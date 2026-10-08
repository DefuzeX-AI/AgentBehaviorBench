from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_draft_flow(client: httpx.Client) -> dict[str, Any]:
    start_payload = {
        "idempotency_key": "smoke-draft-001",
        "disclosure_text": "This is a disclosure text used for end-to-end smoke testing. " * 12,
        "metadata": {"case_id": "SMOKE-DRAFT"},
    }
    start_resp = client.post("/api/v1/draft/start", json=start_payload)
    _assert(start_resp.status_code == 200, f"draft/start failed: {start_resp.text}")
    start_body = start_resp.json()
    _assert(start_body["status"] == "waiting_human", f"draft/start unexpected status: {start_body['status']}")
    _assert("drawing_map" in (start_body.get("data") or {}), "draft/start missing drawing_map")
    _assert("vision_mode" in (start_body.get("data") or {}), "draft/start missing vision_mode")

    session_id = start_body["session_id"]
    claims = start_body["data"]["claims"]
    continue_resp = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    _assert(continue_resp.status_code == 200, f"draft/continue failed: {continue_resp.text}")
    continue_body = continue_resp.json()
    _assert(
        continue_body["status"] in {"completed", "running"},
        f"draft/continue unexpected status: {continue_body['status']}",
    )
    _assert("drawing_map" in (continue_body.get("data") or {}), "draft/continue missing drawing_map")
    return continue_body


def run_oa_flow(client: httpx.Client) -> dict[str, Any]:
    oa_payload = {
        "idempotency_key": "smoke-oa-001",
        "oa_text": "Examiner argues claim 1 lacks inventiveness over a D1 + D2 combination.",
        "original_claims": {"claims": [{"id": 1, "text": "A multi-stage control system..."}]},
        "prior_arts_paths": [],
    }
    oa_resp = client.post("/api/v1/oa/start", json=oa_payload)
    _assert(oa_resp.status_code == 200, f"oa/start failed: {oa_resp.text}")
    oa_body = oa_resp.json()
    _assert(oa_body["status"] in {"completed", "running"}, f"oa/start unexpected status: {oa_body['status']}")
    _assert("visual_report" in (oa_body.get("data") or {}), "oa/start missing visual_report")
    _assert("vision_mode" in (oa_body.get("data") or {}), "oa/start missing vision_mode")
    return oa_body


def main() -> int:
    parser = argparse.ArgumentParser(description="Run E2E smoke test for Draft and OA flows.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--api-key", default="", help="Optional API key for X-API-Key header")
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=30.0) as client:
        draft_result = run_draft_flow(client)
        oa_result = run_oa_flow(client)

    print("SMOKE TEST PASSED")
    print(f"Draft status: {draft_result['status']}")
    print(f"OA status: {oa_result['status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

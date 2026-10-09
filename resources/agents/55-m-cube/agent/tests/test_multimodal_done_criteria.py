from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _draft_start_payload() -> dict[str, object]:
    return {
        "idempotency_key": "mm-done-draft-1",
        "disclosure_text": "这是一份用于多模态验收的技术交底书内容。" * 10,
        "metadata": {"case_id": "MM-DONE-001"},
    }


def test_done_criteria_draft_generates_spec_with_drawing_fields(client: TestClient) -> None:
    start_resp = client.post("/api/v1/draft/start", json=_draft_start_payload())
    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["status"] == "waiting_human"
    assert isinstance(start_body["data"].get("drawing_map"), dict)

    session_id = start_body["session_id"]
    claims = start_body["data"]["claims"]
    cont_resp = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    assert cont_resp.status_code == 200
    cont_body = cont_resp.json()
    specification = cont_body["data"].get("specification") or {}
    assert isinstance(specification, dict)
    assert isinstance(specification.get("title"), str)
    assert isinstance(specification.get("technical_field"), str)
    assert isinstance(specification.get("background_art"), str)
    assert isinstance(specification.get("invention_content"), dict)
    assert isinstance(specification.get("drawings_description"), str)
    assert isinstance(specification.get("detailed_implementation"), dict)


def test_done_criteria_oa_contains_visual_report(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/oa/start",
        json={
            "idempotency_key": "mm-done-oa-1",
            "oa_text": "审查员指出D1图2公开了关键结构特征，请申请人说明差异。",
            "original_claims": {"claims": [{"id": 1, "text": "一种系统..."}]},
            "prior_arts_paths": [],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"completed", "running"}
    assert isinstance(body["data"].get("visual_report"), dict)


def test_done_criteria_vision_fallback_warning_visible(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/oa/start",
        json={
            "idempotency_key": "mm-done-oa-2",
            "oa_text": "审查员引用D1图2与D2图3。",
            "original_claims": {"claims": [{"id": 1, "text": "一种系统..."}]},
            "prior_arts_paths": [],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    warnings = body["data"].get("vision_warnings") or []
    assert isinstance(warnings, list)
    assert len(warnings) >= 1


def test_done_criteria_api_key_not_persisted(client: TestClient) -> None:
    raw_key = "sk-test-should-not-persist"
    resp = client.post(
        "/api/v1/draft/start",
        json=_draft_start_payload(),
        headers={"X-LLM-API-Key": raw_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    serialized = json.dumps(body, ensure_ascii=False)
    # API key should never appear in API payload/session data.
    assert raw_key not in serialized

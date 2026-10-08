from __future__ import annotations

from fastapi.testclient import TestClient


def _start_payload() -> dict[str, object]:
    return {
        "idempotency_key": "idem-1",
        "disclosure_text": "这是一份足够长的技术交底书内容。" * 8,
        "metadata": {"case_id": "CASE-001"},
    }


def test_draft_start_envelope_contract(client: TestClient) -> None:
    resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert set(["request_id", "session_id", "status", "data", "error"]).issubset(body.keys())
    assert body["error"] is None
    assert body["status"] in {"waiting_human", "running"}
    assert "vision_mode" in body["data"]
    assert "drawing_map" in body["data"]


def test_invalid_input_maps_to_e400(client: TestClient) -> None:
    # missing disclosure_text
    resp = client.post("/api/v1/draft/start", json={"idempotency_key": "x"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "E400_INVALID_INPUT"


def test_not_found_maps_to_e404(client: TestClient) -> None:
    resp = client.get("/api/v1/sessions/not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "E404_SESSION_NOT_FOUND"


def test_oa_start_envelope_contract(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/oa/start",
        json={
            "idempotency_key": "oa-1",
            "oa_text": "审查员认为权利要求1不具备创造性。",
            "original_claims": {"claims": [{"id": 1, "text": "一种系统..."}]},
            "prior_arts_paths": [],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(["request_id", "session_id", "status", "data", "error"]).issubset(body.keys())
    assert body["error"] is None
    assert "vision_mode" in body["data"]
    assert "visual_report" in body["data"]
    assert "original_claims" in body["data"]
    assert "original_claims_extracted" in body["data"]
    assert "original_claims_strategy" in body["data"]
    assert "image_recognition_report" in body["data"]
    assert "targeted_reading_audit" in body["data"]


def test_polish_start_envelope_contract(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/polish/start",
        json={
            "idempotency_key": "polish-1",
            "original_claims": {"text": "权利要求书内容"},
            "application_specification": {"text": "说明书内容，包含实施方式与机理描述。"},
            "metadata": {"source": "test"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert set(["request_id", "session_id", "status", "data", "error"]).issubset(body.keys())
    assert "diagnostic_report" in body["data"]
    assert "synergy_feature_vault" in body["data"]
    assert "claim_architecture_plan" in body["data"]
    assert "amplified_specification" in body["data"]
    assert "adversarial_review_report" in body["data"]
    assert "polish_final_package" in body["data"]


def test_file_upload_envelope_contract(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/files/upload",
        data={"purpose": "draft_disclosure"},
        files={"file": ("disclosure.txt", "这是技术交底书内容。".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["data"]["file_id"]
    assert body["data"]["filename"] == "disclosure.txt"
    assert body["data"]["file_kind"] in {"text", "mixed"}
    assert isinstance(body["data"]["image_count"], int)


def test_draft_start_with_uploaded_file_id(client: TestClient) -> None:
    upload_resp = client.post(
        "/api/v1/files/upload",
        data={"purpose": "draft_disclosure"},
        files={"file": ("disclosure.txt", ("这是一份足够长的技术交底书内容。" * 8).encode("utf-8"), "text/plain")},
    )
    assert upload_resp.status_code == 200
    file_id = upload_resp.json()["data"]["file_id"]

    start_resp = client.post(
        "/api/v1/draft/start",
        json={
            "idempotency_key": "idem-file-1",
            "disclosure_file_id": file_id,
            "metadata": {"case_id": "CASE-002"},
        },
    )
    assert start_resp.status_code == 200
    body = start_resp.json()
    assert body["error"] is None
    assert body["status"] in {"waiting_human", "running"}

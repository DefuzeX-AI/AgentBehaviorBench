from __future__ import annotations

from fastapi.testclient import TestClient

from api import routers as routers_module
from api.routers import router


def _start_payload() -> dict[str, object]:
    return {
        "idempotency_key": "idem-flow",
        "disclosure_text": "draft flow test disclosure text. " * 10,
        "metadata": {},
    }


def test_draft_happy_path_start_continue(client: TestClient) -> None:
    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["status"] == "waiting_human"

    session_id = start_body["session_id"]
    claims = start_body["data"]["claims"]

    cont_resp = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    assert cont_resp.status_code == 200
    cont_body = cont_resp.json()
    assert cont_body["status"] in {"completed", "running", "waiting_human"}

    status_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert status_resp.status_code == 200


def test_cancel_session(client: TestClient) -> None:
    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    session_id = start_resp.json()["session_id"]

    cancel_resp = client.post(f"/api/v1/sessions/{session_id}/cancel")
    assert cancel_resp.status_code == 200
    body = cancel_resp.json()
    assert body["status"] == "cancelled"


def test_sse_events_endpoint() -> None:
    matched = [
        route
        for route in router.routes
        if getattr(route, "path", "") == "/api/v1/sessions/{session_id}/events"
    ]
    assert matched, "SSE route not found"
    assert any("GET" in getattr(route, "methods", set()) for route in matched)


def test_draft_continue_uses_targeted_revision_after_logic_review_issue(
    client: TestClient,
    monkeypatch,
) -> None:
    calls = {"count": 0}

    def _fake_logic_review_node(state, agent):
        calls["count"] += 1
        if calls["count"] == 1:
            issues = [
                {
                    "severity": "high",
                    "issue_type": "unsupported_claim",
                    "location": "specification",
                    "description": "need targeted update",
                    "suggestion": "fix only the flagged part",
                }
            ]
        else:
            issues = []
        return {
            "review_issues": issues,
            "current_step": "logic_review_node",
            "status": "running" if issues else "completed",
            "node_latency_ms": 0,
        }

    monkeypatch.setattr("workflows.draft_workflow.logic_review_node", _fake_logic_review_node)
    original_build_graph = routers_module._build_draft_graph_for_runtime

    def _build_graph_force_real(*, llm_runtime, llm_api_key):
        graph, _is_real = original_build_graph(llm_runtime=llm_runtime, llm_api_key=llm_api_key)
        return graph, True

    monkeypatch.setattr("api.routers._build_draft_graph_for_runtime", _build_graph_force_real)

    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]
    claims = start_resp.json()["data"]["claims"]

    first_continue = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    assert first_continue.status_code == 200
    assert first_continue.json()["status"] == "waiting_human"

    second_continue = client.post(
        "/api/v1/draft/continue",
        json={
            "session_id": session_id,
            "approved_claims": claims,
            "apply_targeted_revision": True,
            "revision_instruction": "only revise issues raised by logic_review",
        },
    )
    assert second_continue.status_code == 200
    assert second_continue.json()["status"] in {"completed", "running"}
    assert calls["count"] >= 2


def test_draft_continue_targeted_revision_rejected_in_stub_mode(
    client: TestClient,
    monkeypatch,
) -> None:
    calls = {"count": 0}

    def _fake_logic_review_node(state, agent):
        calls["count"] += 1
        if calls["count"] == 1:
            issues = [
                {
                    "severity": "high",
                    "issue_type": "unsupported_claim",
                    "location": "specification",
                    "description": "need targeted update",
                    "suggestion": "fix only the flagged part",
                }
            ]
        else:
            issues = []
        return {
            "review_issues": issues,
            "current_step": "logic_review_node",
            "status": "running" if issues else "completed",
            "node_latency_ms": 0,
        }

    monkeypatch.setattr("workflows.draft_workflow.logic_review_node", _fake_logic_review_node)

    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]
    claims = start_resp.json()["data"]["claims"]

    first_continue = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    assert first_continue.status_code == 200
    assert first_continue.json()["status"] == "waiting_human"

    second_continue = client.post(
        "/api/v1/draft/continue",
        json={
            "session_id": session_id,
            "approved_claims": claims,
            "apply_targeted_revision": True,
            "revision_instruction": "only revise issues raised by logic_review",
        },
    )
    assert second_continue.status_code == 400
    body = second_continue.json()
    assert body["error"]["code"] == "E400_INVALID_INPUT"
    assert "LLM" in body["error"]["message"]


def test_claims_revise_review_gate_then_auto_revise(client: TestClient, monkeypatch) -> None:
    trace_calls = {"count": 0}

    def _fake_traceability_node(state, agent):
        trace_calls["count"] += 1
        unsupported = trace_calls["count"] == 1
        return {
            "claim_traceability": {
                "reports": [
                    {
                        "claim_number": 1,
                        "elements_evidence": [
                            {
                                "feature_text": "feature A",
                                "verbatim_quote": "not found" if unsupported else "disclosure has feature A",
                                "support_level": "Unsupported" if unsupported else "Explicit",
                                "reasoning": "mock",
                            }
                        ],
                        "is_fully_supported": not unsupported,
                    }
                ],
                "overall_risk_assessment": "mock",
            },
            "current_step": "traceability_check_node",
            "status": "running",
            "node_latency_ms": 0,
        }

    monkeypatch.setattr("workflows.draft_workflow.traceability_check_node", _fake_traceability_node)

    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["status"] == "waiting_human"
    assert start_body["data"]["current_step"] == "claims_revise_review_node"

    session_id = start_body["session_id"]
    cont_resp = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "apply_auto_claim_revision": True},
    )
    assert cont_resp.status_code == 200
    cont_body = cont_resp.json()
    assert cont_body["status"] in {"running", "waiting_human", "completed"}
    assert trace_calls["count"] >= 2


def test_claims_revise_review_manual_claims_skip_auto(client: TestClient, monkeypatch) -> None:
    def _fake_traceability_node(state, agent):
        return {
            "claim_traceability": {
                "reports": [
                    {
                        "claim_number": 1,
                        "elements_evidence": [
                            {
                                "feature_text": "feature A",
                                "verbatim_quote": "not found",
                                "support_level": "Unsupported",
                                "reasoning": "mock",
                            }
                        ],
                        "is_fully_supported": False,
                    }
                ],
                "overall_risk_assessment": "mock",
            },
            "current_step": "traceability_check_node",
            "status": "running",
            "node_latency_ms": 0,
        }

    def _fake_revise_claims_node(state, agent):
        raise AssertionError("revise_claims_node should not run on manual path")

    monkeypatch.setattr("workflows.draft_workflow.traceability_check_node", _fake_traceability_node)
    monkeypatch.setattr("workflows.draft_workflow.revise_claims_node", _fake_revise_claims_node)

    start_resp = client.post("/api/v1/draft/start", json=_start_payload())
    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["status"] == "waiting_human"
    assert start_body["data"]["current_step"] == "claims_revise_review_node"

    session_id = start_body["session_id"]
    claims = start_body["data"]["claims"]
    cont_resp = client.post(
        "/api/v1/draft/continue",
        json={"session_id": session_id, "approved_claims": claims},
    )
    assert cont_resp.status_code == 200

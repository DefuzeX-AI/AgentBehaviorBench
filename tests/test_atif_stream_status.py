"""Provider terminal errors survive ATIF conversion despite successful HTTP."""
import json
import pytest
from agentbench.trajectory.atif.reader import read_evidence


@pytest.mark.parametrize("kind,status", [("error", "error"), ("response.failed", "error"), ("response.incomplete", "incomplete")])
def test_stream_terminal_status(tmp_path, kind, status):
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "test", "status": "completed"}), encoding="utf-8")
    rows = [
        {"event": "llm_request", "timestamp": "2026-11-15T12:00:00Z", "data": {"call_id": "c", "payload": {"messages": []}}},
        {"event": "llm_response", "timestamp": "2026-11-15T12:00:01Z", "data": {"call_id": "c", "status": 200, "payload": {"events": [{"type": kind, "error": {"message": "provider stopped"}}]}}},
    ]
    (tmp_path / "network.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    bundle = read_evidence(tmp_path)
    assert bundle.models[0]["status"] == status
    assert bundle.models[0]["error"][0]["type"] == kind

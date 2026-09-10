import json
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from agentbench.cli.viewer import parse_result_log, start_viewer_server


def test_parse_result_log_groups_events_and_reports_invalid_entries(tmp_path) -> None:
    result_log = tmp_path / "result-20260819-010101.json"
    events = [
        {
            "event": "run_started",
            "suite_id": "suite_test",
            "selected_agent_ids": ["agent-a"],
        },
        {
            "event": "step_started",
            "agent_id": "agent-a",
            "input_id": "input-a",
            "payload": {"prompt": "hello"},
        },
        {
            "event": "step_completed",
            "agent_id": "agent-a",
            "step": {
                "input_id": "input-a",
                "payload": {"prompt": "hello"},
                "output": {"answer": "ok"},
                "raw_output": {"node": "final"},
            },
        },
        {
            "event": "agent_completed",
            "agent_id": "agent-a",
            "item": {
                "agent_id": "agent-a",
                "benchmark": {
                    "passed": True,
                    "steps": [
                        {
                            "input_id": "input-a",
                            "payload": {"prompt": "hello"},
                            "output": {"answer": "ok"},
                            "raw_output": {"node": "final"},
                        }
                    ],
                },
                "error": None,
            },
        },
        {"event": "suite_completed", "summary": {"suite_passed": True}},
    ]
    result_log.write_text(
        json.dumps([*events, "invalid event"]),
        encoding="utf-8",
    )

    parsed = parse_result_log(result_log)

    assert parsed["state"] == "complete"
    assert parsed["suite_id"] == "suite_test"
    assert parsed["selected_agent_ids"] == ["agent-a"]
    assert parsed["summary"] == {"suite_passed": True}
    assert parsed["event_count"] == 5
    assert parsed["parse_errors"] == [
        {"index": 5, "message": "Expected JSON object"}
    ]
    assert parsed["agents"][0]["agent_id"] == "agent-a"
    assert [event["event"] for event in parsed["agents"][0]["step_events"]] == [
        "step_started",
        "step_completed",
    ]


def test_parse_result_log_surfaces_step_events_without_agent_result(tmp_path) -> None:
    result_log = tmp_path / "result.json"
    result_log.write_text(json.dumps([
        {"event": "run_started", "selected_agent_ids": ["agent-a"]},
        {"event": "step_started", "agent_id": "agent-a", "input_id": "input-a",
         "payload": {"prompt": "kept case"}},
    ]), encoding="utf-8")

    parsed = parse_result_log(result_log)

    assert parsed["state"] == "running_or_interrupted"
    assert parsed["suite_id"] is None
    assert parsed["agents"] == [
        {
            "agent_id": "agent-a",
            "benchmark": None,
            "error": {
                "type": "Incomplete",
                "message": "Agent did not produce a final suite result.",
            },
            "step_events": [
                {
                    "event": "step_started",
                    "agent_id": "agent-a",
                    "input_id": "input-a",
                    "payload": {"prompt": "kept case"},
                }
            ],
        }
    ]


def test_viewer_serves_static_app_and_live_result_api(tmp_path, monkeypatch) -> None:
    from agentbench.cli import viewer as viewer_module
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text('<html><head><title>ABB · Trace</title></head><body></body></html>')
    monkeypatch.setattr(viewer_module, "WEB_ROOT", assets)
    result_log = tmp_path / "result.json"
    result_log.write_text(json.dumps([
        {"event": "run_started", "suite_id": "suite_test", "selected_agent_ids": ["agent-a"]},
    ]), encoding="utf-8")
    viewer = start_viewer_server(result_log, port=0)

    try:
        with urlopen(f"{viewer.base_url}/api/health", timeout=2) as response:
            health = json.load(response)
        with urlopen(
            f"{viewer.base_url}/api/suites/suite_test/result", timeout=2
        ) as response:
            result = json.load(response)
        with urlopen(viewer.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"{viewer.base_url}/api/suites/suite_wrong/result", timeout=2
            )
    finally:
        viewer.stop()

    assert health == {"ok": True}
    assert viewer.url.endswith("/suite/suite_test/")
    assert result["selected_agent_ids"] == ["agent-a"]
    assert error.value.code == 409
    assert "<title>ABB · Trace</title>" in html
    assert 'name="abb-result-api"' in html
    assert '/api/suites/suite_test/result' in html
    assert result["events"][0]["event"] == "run_started"
    assert not viewer.thread.is_alive()


def test_viewer_explains_missing_frontend_build(tmp_path, monkeypatch):
    from agentbench.cli import viewer as viewer_module
    monkeypatch.setattr(viewer_module, "WEB_ROOT", tmp_path / "missing-dist")
    result = tmp_path / "result.json"
    result.write_text('[]')
    with pytest.raises(viewer_module.ViewerUnavailable, match="npm ci.*npm run build"):
        start_viewer_server(result, port=0)

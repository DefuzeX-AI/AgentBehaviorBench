from agentbench.adapter.acp.process import child_environment
from agentbench.harness.otel.config import parse_config
from agentbench.harness.otel.profiles.native import environment
from types import SimpleNamespace
import json


def test_target_and_tool_environments_are_distinct():
    assert parse_config({}).profile == "unconfigured"
    cfg = parse_config({"otel": {"profile": "openclaw"}})
    target = environment(cfg, "http://127.0.0.1:1234", "openclaw")
    adapter = SimpleNamespace(env_keys=())
    assert "ABB_OTEL_PROFILE" not in child_environment(adapter)
    patch = json.loads(child_environment(adapter, target=target)["ABB_OTEL_GATEWAY_CONFIG"])
    assert patch["diagnostics"]["otel"]["captureContent"]
    assert patch["plugins"]["entries"]["diagnostics-otel"]["enabled"]
    assert patch["diagnostics"]["otel"]["endpoint"].startswith("http://127.0.0.1:")


def test_llxprt_spool_skips_metrics_and_keeps_original(tmp_path):
    from agentbench.harness.otel import create_session
    from pathlib import Path
    cfg = parse_config({"otel": {"profile": "file-export", "file": "trace.jsonl", "file_format": "llxprt-jsonl"}})
    session = create_session(cfg, tmp_path, "llxprt-code")
    path = Path(session.environment["ABB_OTEL_FILE"])
    span = {"name": "read", "spanContext": {"traceId": "10" * 16, "spanId": "20" * 8},
            "startTime": [10, 123], "endTime": [11, 234], "attributes": {"output.value": "77"},
            "instrumentationScope": {"name": "llxprt"}}
    path.write_text(json.dumps({"metric": "other"}) + "\n" + json.dumps(span) + "\n")
    session.close()
    row = json.loads((tmp_path / "spans.jsonl").read_text())
    assert row["span"]["startTimeUnixNano"] == "10000000123"
    assert row["file_record"] == span and row["transport"] == "llxprt-file"


def test_openclaw_can_disable_content_capture():
    cfg = parse_config({"otel": {"profile": "openclaw", "capture_content": False}})
    env = environment(cfg, "http://127.0.0.1:1234", "openclaw")
    assert json.loads(env["ABB_OTEL_GATEWAY_CONFIG"])["diagnostics"]["otel"]["captureContent"] is False

def test_opensoul_reports_gateway_plugin_failure(tmp_path):
    from pathlib import Path
    from agentbench.harness.otel import create_session
    session = create_session(parse_config({"otel": {"profile": "opensoul"}}), tmp_path, "opensoul")
    log = Path(session.environment["ABB_OTEL_GATEWAY_LOG"])
    log.write_text("[plugins] plugin service failed (diagnostics-otel): TypeError: Resource is not a constructor\n")
    session.close()
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["status"] == "incomplete" and status["span_count"] == 0
    assert status["reason"].endswith("Resource is not a constructor")

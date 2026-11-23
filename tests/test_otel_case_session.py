import json
from agentbench.harness.otel import create_session
from agentbench.harness.otel.config import CaptureConfig


def test_delayed_export_and_isolated_cases(tmp_path):
    first, second = [create_session(CaptureConfig("native-otlp"), tmp_path / case, case) for case in ("A", "B")]
    try:
        assert first.receiver.endpoint != second.receiver.endpoint
        first.sink.accept_json({"resourceSpans": [{"scopeSpans": [{"spans": [{
            "traceId": "11"*16, "spanId": "22"*8, "name": "late child"}]}]}]}, transport="test")
    finally:
        first.close()
        second.close()
    assert json.loads((tmp_path / "A/status.json").read_text())["status"] == "received"
    assert json.loads((tmp_path / "B/status.json").read_text())["status"] == "zero_spans"
    record = json.loads((tmp_path / "A/spans.jsonl").read_text())
    assert "input_id" not in record and "input_id" not in record["span"]


def test_persistent_adapter_flushes_after_last_input(tmp_path, monkeypatch):
    import asyncio
    from urllib.request import Request, urlopen
    from agentbench.runtime.agentcontainer.session import AgentSession, DEFAULT_ADAPTER_FACTORY

    class Agent:
        def load(self):
            self.endpoint = self.trace_environment["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]

        async def aclose(self):
            span = {"name": "last child", "traceId": "aa" * 16, "spanId": "bb" * 8}
            batch = {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}
            with urlopen(Request(self.endpoint, data=json.dumps(batch).encode(),
                                 headers={"Content-Type": "application/json"})) as response:
                assert response.status == 200

    (tmp_path / "agent.toml").write_text('[otel]\nprofile="native-otlp"\n')
    monkeypatch.setattr(DEFAULT_ADAPTER_FACTORY, "create", lambda *_: Agent())
    session = AgentSession()
    session.capture_directory = tmp_path / "attempt" / "otel"
    first = session.load(tmp_path, dict(agent_id="agent", framework="acp", run_id="i1", session_id="case"))
    second = session.load(tmp_path, dict(agent_id="agent", framework="acp", run_id="i2", session_id="case"))
    assert first is second and not (session.capture_directory / "spans.jsonl").exists()
    asyncio.run(session.aclose())
    assert json.loads((session.capture_directory / "status.json").read_text())["span_count"] == 1
    saved = json.loads((session.capture_directory / "spans.jsonl").read_text())
    assert saved["ref"] == {"file": "otel/spans.jsonl", "line": 1}
    assert "input_id" not in saved["context"]


def test_gateway_finishes_export_after_bridge_exits(tmp_path):
    import asyncio
    import os
    import sys
    import pytest
    from agentbench.adapter.acp.process import terminate_group
    if os.name != "posix":
        pytest.skip("POSIX process groups")
    child = """
import pathlib, signal, sys, time
from urllib.request import Request, urlopen
def flush(*args):
    time.sleep(0.15)
    with urlopen(Request(sys.argv[1], data=sys.argv[2].encode(), headers={"Content-Type":"application/json"})) as response:
        assert response.status == 200
    sys.exit(0)
signal.signal(signal.SIGTERM, flush)
pathlib.Path(sys.argv[3]).touch()
while True: signal.pause()
"""
    async def run():
        session = create_session(CaptureConfig("native-otlp"), tmp_path / "otel", "bridge")
        ready = tmp_path / "ready"
        span = {"traceId": "31"*16, "spanId": "42"*8, "name": "gateway shutdown"}
        batch = {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}
        bridge = await asyncio.create_subprocess_exec(sys.executable, "-c",
            "import subprocess,sys,time; subprocess.Popen(sys.argv[1:]); time.sleep(30)",
            sys.executable, "-c", child, session.receiver.endpoint + "/v1/traces", json.dumps(batch), str(ready),
            start_new_session=True)
        try:
            for _ in range(300):
                if ready.exists():
                    break
                await asyncio.sleep(0.01)
            assert ready.exists()
        finally:
            await terminate_group(bridge, 2, flush_descendants=True)
            session.close()
    asyncio.run(run())
    assert json.loads((tmp_path / "otel/status.json").read_text())["span_count"] == 1


def test_in_process_agent_receives_trace_file_path(tmp_path, monkeypatch):
    import asyncio
    import os
    from agentbench.runtime.agentcontainer.session import AgentSession, DEFAULT_ADAPTER_FACTORY

    span = {"traceId": "ab" * 16, "spanId": "cd" * 8, "name": "file export"}

    class Agent:
        def load(self):
            # An in-process exporter reads its output path when the Agent loads.
            self.path = os.environ["ABB_OTEL_FILE"]

        def close(self):
            with open(self.path, "w", encoding="utf-8") as stream:
                json.dump({"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}, stream)

    (tmp_path / "agent.toml").write_text('[otel]\nprofile="file-export"\nfile="trace.json"\n')
    monkeypatch.setattr(DEFAULT_ADAPTER_FACTORY, "create", lambda *_: Agent())
    monkeypatch.delenv("ABB_OTEL_FILE", raising=False)
    session = AgentSession()
    session.capture_directory = tmp_path / "attempt" / "otel"
    session.load(tmp_path, dict(agent_id="agent", framework="langgraph", run_id="i1", session_id="case"))
    asyncio.run(session.aclose())

    status = json.loads((session.capture_directory / "status.json").read_text())
    assert status["status"] == "received" and status["span_count"] == 1
    assert json.loads((session.capture_directory / "spans.jsonl").read_text())["transport"] == "file"
    assert "ABB_OTEL_FILE" not in os.environ

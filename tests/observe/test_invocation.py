import asyncio
import json
import subprocess
import time
from types import SimpleNamespace
import pytest

from agentbench.runtime.agentcontainer.invocation import invoke_once
from agentbench.runtime.agentcontainer.adapter import ContainerAgentAdapter


class Runtime:
    def __init__(self, root, mode="good"):
        self.artifact_root, self.mode, self.run_id = root, mode, "session"
        self.closed = False
        self.timeout = 2

    def invocation_timeout(self, agent):
        return self.timeout

    def start(self, agent, *, invocation):
        inputs, outputs = invocation
        request = json.loads((inputs / "request.json").read_text())
        result = {"schema": "abb.result.v1", "run_id": request["run_id"],
                  "agent_id": agent.agent_id, "status": "succeeded", "output": request["input"], "raw_output": {}}
        if self.mode == "foreign":
            result["run_id"] = "previous-run"
        if self.mode == "incomplete":
            del result["output"]
        if self.mode != "missing":
            (outputs / "result.json").write_text("{" if self.mode == "corrupt" else json.dumps(result))
        owner = self

        class Session:
            stdout = "diagnostic"
            stderr = ""
            returncode = 1 if owner.mode == "nonzero" else 0

            def wait(self, timeout):
                if owner.mode == "timeout":
                    time.sleep(min(timeout, 0.01))
                    raise subprocess.TimeoutExpired("offline", timeout)
                return self.returncode

            def close(self):
                owner.closed = True

            def validate_trace(self, value):
                assert value == 0
        return Session()


@pytest.mark.parametrize("mode", ["foreign", "incomplete", "missing", "corrupt", "nonzero", "timeout"])
def test_failed_delivery_never_succeeds_and_always_cleans(tmp_path, mode):
    runtime = Runtime(tmp_path, mode)
    runtime.timeout = 0.02
    with pytest.raises((RuntimeError, ValueError, TimeoutError)):
        invoke_once(runtime, SimpleNamespace(agent_id="test", framework="langgraph"), {"text": "中文"})
    assert runtime.closed
    assert len(list(tmp_path.rglob("diagnostics.json"))) == 1


def test_same_session_has_distinct_invocation_ids(tmp_path):
    runtime = Runtime(tmp_path)
    agent = SimpleNamespace(agent_id="test", framework="langgraph")
    assert invoke_once(runtime, agent, "first").output == "first"
    assert invoke_once(runtime, agent, "second").output == "second"
    requests = [json.loads(path.read_text()) for path in tmp_path.rglob("request.json")]
    assert len({r["run_id"] for r in requests}) == 2
    assert {r["session_id"] for r in requests} == {"session"}


def test_async_cancellation_waits_for_cleanup(offline_agent, tmp_path):
    runtime = Runtime(tmp_path / "artifacts", "timeout")
    adapter = ContainerAgentAdapter(offline_agent, runtime)

    async def run():
        task = asyncio.create_task(adapter.ainvoke({"number": 1}))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.closed
    asyncio.run(run())

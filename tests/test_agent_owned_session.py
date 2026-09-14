"""Native memory acceptance: real KUMA, container worker, LangGraph and SQLite."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

import pytest

from tests.sdk_fixtures.agent_owned_session import execute_case, write_agent
from agentbench.runtime.docker.policy import DockerPolicy


@pytest.mark.parametrize("turns", [3, 5])
def test_current_inputs_reach_persistent_agent_owned_sqlite(tmp_path, turns):
    root = tmp_path / "unit"
    write_agent(root)
    inputs = ["remember blue", "recall", "remember green", "recall", "recall"][:turns]
    expected = ["blue", "blue", "green", "green", "green"][:turns]
    output = tmp_path / "output"
    check = asyncio.run(execute_case(root, tmp_path / "work", output, inputs, expected))

    assert check["exit_code"] == 0
    assert check["inputs"] == inputs
    assert check["outputs"] == expected
    assert [row[0] for row in check["database_turns"]] == inputs
    session_id, = set(check["session_ids"])
    assert {row[1] for row in check["database_turns"]} == {session_id}
    assert len(set(check["invocation_ids"])) == turns
    assert [item["raw_output"]["turn"] for item in check["results"]] == list(range(1, turns + 1))
    assert [item["raw_output"]["received"] for item in check["results"]] == inputs
    assert {item["raw_output"]["pid"] for item in check["results"]} == {check["session"]["pid"]}
    assert check["session"]["adapter_initializations"] == 1
    assert check["session"]["invocations"] == turns
    assert check["session"]["closed"] is True
    assert check["agent_close"] == {"closed": True, "close_count": 1}
    assert check["judge_calls"] == [{"outputs": expected, "statuses": ["completed"] * turns}]
    assert check["manifest"]["evidence"] == "captured"
    assert check["manifest"]["otel"] == "complete"
    assert (output / "case.json").is_file()
    assert json.loads((output / "judge/report.json").read_text())["status"] == "pass"


def test_another_case_has_a_fresh_agent_database_and_session(tmp_path):
    root = tmp_path / "unit"
    write_agent(root)
    async def run_both():
        first = await execute_case(root, tmp_path / "work-one", tmp_path / "output-one",
                                   ["remember private-first", "recall", "recall"], ["private-first"] * 3)
        second = await execute_case(root, tmp_path / "work-two", tmp_path / "output-two",
                                    ["recall", "remember second", "recall"], ["unset", "second", "second"])
        return first, second
    first, second = asyncio.run(run_both())
    assert first["exit_code"] == second["exit_code"] == 0
    assert first["session_ids"][0] != second["session_ids"][0]
    assert second["outputs"][0] == "unset"
    assert "private-first" not in json.dumps(second["database_turns"])
    assert first["agent_close"] == second["agent_close"] == {"closed": True, "close_count": 1}


@pytest.mark.parametrize("terminal,status", [("fail", "failed"), ("cancel", "cancelled")])
def test_agent_failure_or_cancellation_closes_native_sqlite(tmp_path, terminal, status):
    root = tmp_path / "unit"
    write_agent(root)
    output = tmp_path / "output"
    check = asyncio.run(execute_case(root, tmp_path / "work", output,
        ["remember blue", "recall", terminal], ["blue", "blue", None]))
    assert check["exit_code"] == 1
    assert check["results"][-1]["status"] == status
    assert check["outputs"][:2] == ["blue", "blue"]
    assert check["session"]["closed"] is True
    assert check["agent_close"] == {"closed": True, "close_count": 1}
    assert check["manifest"]["execution"] == "failed"
    assert all(step["committed"] for step in check["manifest"]["steps"])
    assert check["manifest"]["judge"] == "received"
    assert (output / "inputs/0001/submission.json").is_file()
    assert (output / "inputs/0002/submission.json").is_file()


def test_shared_session_rejects_thread_switch_and_use_after_close(tmp_path, monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from agentbench.runtime.agentcontainer.session import AgentSession
    from agentbench.runtime.agentcontainer.worker import execute

    root = tmp_path / "unit"
    write_agent(root)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    provider = TracerProvider()
    session = AgentSession()
    async def invoke(number, payload, thread_id):
        folder = tmp_path / f"invocation-{number}"
        folder.mkdir()
        request = folder / "request.json"
        request.write_text(json.dumps({"schema": "abb.invocation.v1", "run_id": f"invoke-{number}",
            "session_id": "case-session", "agent_id": "sqlite-memory-acceptance", "framework": "langgraph",
            "input": payload, "config": {"configurable": {"thread_id": thread_id}}}))
        code = await execute(root, request, folder, provider=provider, session=session)
        return code, json.loads((folder / "result.json").read_text())

    async def scenario():
        try:
            first = await invoke(1, "remember original", "case-session")
            conflict = await invoke(2, "remember leaked", "another-session")
            recall = await invoke(3, "recall", "case-session")
            await session.aclose()
            closed = await invoke(4, "recall", "case-session")
            return first, conflict, recall, closed
        finally:
            await session.aclose()
            provider.shutdown()

    first, conflict, recall, closed = asyncio.run(scenario())
    assert first[0] == recall[0] == 0
    assert recall[1]["output"] == "original"
    assert conflict[0] == closed[0] == 1
    assert conflict[1]["error_type"] == closed[1]["error_type"] == "ValueError"
    assert recall[1]["raw_output"]["turn"] == 2
    assert session.snapshot()["invocations"] == 2
    assert session.snapshot()["closed"] is True
    assert json.loads((work / "agent-closed.json").read_text()) == {"closed": True, "close_count": 1}


@pytest.mark.skipif(not os.getenv("ABB_AGENT_SESSION_IMAGE"), reason="Opt-in existing Python/KUMA/LangGraph image")
def test_real_container_retains_native_session_case_outputs_and_judge():
    """Use current source and cached dependencies with all network disabled."""
    repository = Path(__file__).resolve().parents[1]
    output = repository / "results/verification" / f"agent-owned-session-{uuid4().hex}"
    output.mkdir(parents=True)
    image = os.environ["ABB_AGENT_SESSION_IMAGE"]
    command = ["docker", "run", "--rm", "--network", "none", *DockerPolicy().run_arguments(),
        "--user", "10001:10001", "--workdir", "/tmp",
        "--env", "PYTHONPATH=/opt/abb-current-runtime", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "KUMA_API_KEY=", "--env", "DEFUZEX_API_KEY=",
        "--mount", f"type=bind,source={repository / 'agentbench'},target=/opt/abb-current-runtime/agentbench,readonly",
        "--mount", f"type=bind,source={repository / 'tests/sdk_fixtures'},target=/checks,readonly"]
    def launch(name):
        case = output / name
        case.mkdir()
        started = time.monotonic()
        process = subprocess.run([*command,
            "--mount", f"type=bind,source={case},target=/artifacts",
            "--entrypoint", "python", image, "/checks/agent_owned_session.py", "--scenario", name],
            capture_output=True, text=True, timeout=120)
        finished = time.monotonic()
        (case / "container.log").write_text(process.stdout + process.stderr)
        assert process.returncode == 0, f"See {case / 'container.log'}"
        return name, started, finished

    with ThreadPoolExecutor(max_workers=3) as workers:
        runs = list(workers.map(launch, ("five-turns", "fresh-case", "failure")))
    assert max(run[1] for run in runs) < min(run[2] for run in runs)
    sessions = []
    for name, _, _ in runs:
        case = output / name
        report = json.loads((case / "acceptance.json").read_text())
        assert report["status"] == "passed"
        assert report["network"] == "none"
        assert report["providers"] == "offline-custom"
        check = json.loads((case / "verification.json").read_text())
        sessions.append(check["session_ids"][0])
        assert check["runtime"].startswith("/opt/abb-current-runtime/")
        assert (case / "case.json").is_file()
        assert (case / "inputs/0001/result.json").is_file()
        assert json.loads((case / "judge/report.json").read_text())["status"] == "pass"
    assert len(set(sessions)) == len(sessions)
    (output / "verification.json").write_text(json.dumps({"status": "passed", "image": image,
        "network": "none", "providers": "offline-custom", "concurrent_containers": 3,
        "same_database_path": "/tmp/session-work/case/agent-memory.sqlite3",
        "containers": [{"scenario": name, "started": start, "finished": finish}
                       for name, start, finish in runs]}, indent=2))
    print(f"Agent-owned SQLite acceptance artifacts retained: {output}", flush=True)

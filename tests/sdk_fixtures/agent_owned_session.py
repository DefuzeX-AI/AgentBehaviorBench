"""Offline acceptance through real PyPI KUMA and the production Agent worker.

The custom providers only replace remote Case generation and Judge services.
The fixture Agent owns its SQLite database; BBA has no database API or history
injection. This file also runs directly inside an existing runtime image.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import chdir
from importlib.metadata import version
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
from uuid import uuid4


AGENT_SOURCE = '''"""A deterministic Agent with its own SQLite memory and lifecycle."""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict, total=False):
    question: str
    answer: str
    thread_id: str
    received: str
    turn: int
    pid: int


class MemoryAgent:
    def __init__(self):
        self.directory = Path.cwd()
        self.database = sqlite3.connect(self.directory / "agent-memory.sqlite3", check_same_thread=False)
        self.database.execute("CREATE TABLE IF NOT EXISTS memory (value TEXT)")
        self.database.execute("CREATE TABLE IF NOT EXISTS turns (input TEXT, thread_id TEXT)")
        graph = StateGraph(State)
        graph.add_node("remember_or_recall", self.respond)
        graph.add_edge(START, "remember_or_recall")
        graph.add_edge("remember_or_recall", END)
        self.graph = graph.compile()

    def respond(self, state, config):
        question = state["question"]
        thread_id = config["configurable"]["thread_id"]
        self.database.execute("INSERT INTO turns VALUES (?, ?)", (question, thread_id))
        self.database.commit()
        if question == "fail":
            raise RuntimeError("Intentional Agent failure after committed SQLite work")
        if question == "cancel":
            raise asyncio.CancelledError("Intentional cancellation")
        if question.startswith("remember "):
            self.database.execute("DELETE FROM memory")
            self.database.execute("INSERT INTO memory VALUES (?)", (question.removeprefix("remember "),))
            self.database.commit()
        row = self.database.execute("SELECT value FROM memory").fetchone()
        count = self.database.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        return {"answer": row[0] if row else "unset", "received": question,
                "thread_id": thread_id, "turn": count, "pid": os.getpid()}

    def invoke(self, value, config=None):
        return self.graph.invoke(value, config=config)

    async def ainvoke(self, value, config=None):
        if value["question"] == "cancel":
            # Cancel at the Agent invocation boundary. A cancellation raised
            # inside a LangGraph node is deliberately wrapped by LangGraph as
            # NodeCancelledError, which is a graph failure instead.
            return self.respond(value, config)
        return await self.graph.ainvoke(value, config=config)

    def close(self):
        self.database.close()
        marker = self.directory / "agent-closed.json"
        count = json.loads(marker.read_text())["close_count"] if marker.exists() else 0
        marker.write_text(json.dumps({"closed": True, "close_count": count + 1}))


def create_graph():
    return MemoryAgent()
'''


def write_agent(root: Path) -> None:
    """Create a native LangGraph entrypoint with an identity-only input contract."""
    source = root / "agent"
    source.mkdir(parents=True)
    name = "sqlite_agent_" + uuid4().hex
    (source / f"{name}.py").write_text(AGENT_SOURCE)
    (source / "langgraph.json").write_text(json.dumps({"graphs": {"memory": f"{name}.py:create_graph"}}))
    (root / "agent.toml").write_text(
        'agent_id = "sqlite-memory-acceptance"\nframework = "langgraph"\n'
        '[adapter]\ntype = "langgraph"\nconfig = "langgraph.json"\n'
        'graph_id = "memory"\ninput_key = "question"\noutput_key = "answer"\n'
    )
    (root / "evaluation").mkdir()
    (root / "evaluation/input-contract.json").write_text('{"encoding": "identity"}')
    (source / "profile.md").write_text(
        '---\nagent_description: Remember and recall values using Agent-owned SQLite.\n'
        'input_type: text\n---\n## Production Use Scenario\n'
        'Users ask to remember a value and recall it in the same session.\n'
        '## Behaviors to Test\nRemember corrections and isolate independent sessions.\n'
        '## Known Limitations or Prohibited Behaviors\nNo external network calls.\n'
    )


async def execute_case(root: Path, work: Path, output: Path, inputs: list[str], expected: list[str | None],
                       *, allow_local: bool = True):
    """Run a saved real SDK Case through the production KUMA container worker.

    Args:
        root: Readable Agent unit containing its native graph entrypoint.
        work: This Case's writable current directory, owned by its process.
        output: Persistent BBA evidence directory, separate from Agent storage.
        inputs: Current-turn text payloads, delivered by real KUMA in order.
        expected: Independently specified answers for the local Judge.
        allow_local: Explicit SDK opt-in for host tests; false in real containers.
    Returns:
        Serializable verification metadata; Case/output/Judge remain on disk.
    """
    from kuma import create_run as real_create_run
    from agentbench.sdk.common.case_identity import case_content_sha256
    from agentbench.sdk.plugin.kuma.compatibility import run_case
    from agentbench.sdk.plugin.kuma.worker import execute
    import agentbench.runtime.agentcontainer.worker as generic_worker

    work.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    case_id = "sqlite-case-" + uuid4().hex
    case = {"case_id": case_id, "input_type": "text", "inputs": [
        {"input_id": f"turn-{i + 1}", "payload_type": "text", "payload": payload}
        for i, payload in enumerate(inputs)
    ]}
    prepared = real_create_run(
        repo_path=root / "agent", agent_profile_path=root / "agent/profile.md",
        case_provider=lambda context: case, judge=False, allow_local=allow_local,
        track_files=False, max_steps=len(inputs),
    )
    case_path = root / "agent" / f"{case_id}.json"
    try:
        prepared.save_case(case_path)
        expected_identity = {"case_id": prepared.case_id,
                             "content_sha256": case_content_sha256(run_case(prepared))}
    finally:
        prepared.cancel()

    judged = []
    def judge(context):
        actual = [item.submission.output for item in context.history]
        assert actual == expected
        assert [item.test_input.payload for item in context.history] == inputs
        judged.append({"outputs": actual, "statuses": [item.submission.status for item in context.history]})
        return {"status": "pass", "summary": "Offline custom Judge verified Agent-owned SQLite; no service evaluation.",
                "issues": []}

    def local_create_run(**options):
        options["allow_local"] = allow_local
        return real_create_run(**options, judge_provider=judge)

    # Only the remote-service selection is replaced. execute(), drive_run(),
    # AgentSession, LangGraphAdapter, LangGraph and SQLite all execute normally.
    with patch("kuma.create_run", side_effect=local_create_run), patch.dict(
        "os.environ", {"KUMA_API_KEY": "offline-provider-not-a-credential"}
    ), chdir(work):
        code = await execute(root, output, {"case_artifact": str(case_path),
            "expected_case": expected_identity, "max_steps": len(inputs)})

    steps = sorted((output / "inputs").glob("*"))
    assert steps, (output / "error.json").read_text() if (output / "error.json").exists() else "No Agent inputs"
    requests = [json.loads((step / "request.json").read_text()) for step in steps]
    results = [json.loads((step / "result.json").read_text()) for step in steps]
    connection = sqlite3.connect(work / "agent-memory.sqlite3")
    try:
        database_turns = connection.execute("SELECT input, thread_id FROM turns ORDER BY rowid").fetchall()
    finally:
        connection.close()
    verification = {
        "exit_code": code, "inputs": [request["input"] for request in requests],
        "session_ids": [request["session_id"] for request in requests],
        "invocation_ids": [request["run_id"] for request in requests],
        "outputs": [result.get("output") for result in results], "results": results,
        "database_turns": database_turns, "judge_calls": judged,
        "session": json.loads((output / "session.json").read_text()),
        "agent_close": json.loads((work / "agent-closed.json").read_text()),
        "manifest": json.loads((output / "manifest.json").read_text()),
        "sdk_version": version("kuma-defuzex"), "runtime": generic_worker.__file__,
        "providers": "offline-custom", "production_services_called": False,
    }
    (output / "verification.json").write_text(json.dumps(verification, indent=2))
    return verification


async def main(output: Path, workspace: Path, scenario: str):
    root = workspace / "unit"
    write_agent(root)
    cases = [
        ("five-turns", ["remember blue", "recall", "remember green", "recall", "recall"],
         ["blue", "blue", "green", "green", "green"]),
        ("fresh-case", ["recall", "remember orange", "recall"], ["unset", "orange", "orange"]),
        ("failure", ["remember blue", "recall", "fail"], ["blue", "blue", None]),
    ]
    checks = {}
    for name, inputs, expected in cases:
        if name != scenario:
            continue
        # Every independent container deliberately uses the identical SQLite
        # pathname. The production /tmp tmpfs, not an Agent-specific BBA store,
        # provides the process boundary that keeps different Cases isolated.
        check = await execute_case(root, workspace / "case", output, inputs, expected, allow_local=False)
        assert check["inputs"] == inputs
        assert check["outputs"] == expected
        assert check["session"]["adapter_initializations"] == 1
        assert check["session"]["invocations"] == len(inputs)
        assert check["session"]["closed"] is True
        assert check["agent_close"] == {"closed": True, "close_count": 1}
        assert len(set(check["session_ids"])) == 1
        assert check["manifest"]["judge"] == "received"
        assert check["exit_code"] == (1 if name == "failure" else 0)
        checks[name] = {"exit_code": check["exit_code"], "session_id": check["session_ids"][0]}
    assert len({check["session_id"] for check in checks.values()}) == len(checks)
    (output / "acceptance.json").write_text(json.dumps({"status": "passed", "cases": checks,
        "network": "none", "providers": "offline-custom", "sdk_version": version("kuma-defuzex")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/artifacts"))
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/session-work"))
    parser.add_argument("--scenario", choices=("five-turns", "fresh-case", "failure"), default="five-turns")
    args = parser.parse_args()
    asyncio.run(main(args.output.resolve(), args.workspace.resolve(), args.scenario))

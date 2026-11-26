"""agentbench chat: one Agent session across turns, exchanged through the file mailbox."""
import asyncio
import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.observe import chat as host
from agentbench.runtime.agentcontainer import chat as worker
from agentbench.runtime.agentcontainer import mailbox

MANIFEST = ('agent_id = "demo"\nframework = "acp"\n'
            '[runtime]\ntype = "docker"\nexecution = "oneshot"\n'
            '[launch]\nargv = ["python", "-m", "agentbench.runtime.agentcontainer.worker"]\n')


def unit(tmp_path):
    root = tmp_path / "unit"
    root.mkdir()
    (root / "agent.toml").write_text(MANIFEST, encoding="utf-8")
    return root


class FakeAgentSession:
    def __init__(self):
        self.closed = False
        self.history = []

    async def aclose(self):
        self.closed = True


def fake_invoke(fail_on=None):
    async def invoke(root, request, output, *, session):
        envelope = json.loads(Path(request).read_text(encoding="utf-8"))
        session.history.append(envelope)
        failed = envelope["input"] == fail_on
        result = {"schema": "abb.result.v1", "run_id": envelope["run_id"], "agent_id": envelope["agent_id"],
                  "status": "failed" if failed else "succeeded",
                  "output": None if failed else f"reply {len(session.history)}: {envelope['input']}"}
        if failed:
            result.update(error="boom", session_usable=False)
        (Path(output) / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return 0 if not failed else 1
    return invoke


def serve(root, inbox, output, session, **kwargs):
    return asyncio.run(worker.serve(root, inbox, output, session_id="chat-1", session=session,
                                    invoke=fake_invoke(**kwargs), publish=lambda path: None, poll=0.01))


def test_worker_answers_turns_in_one_session_until_end(tmp_path):
    root, inbox, output = unit(tmp_path), tmp_path / "in", tmp_path / "out"
    mailbox.post(mailbox.turn_path(inbox, 1), mailbox.turn(1, "hi"))
    mailbox.post(mailbox.turn_path(inbox, 2), mailbox.turn(2, "again"))
    mailbox.post(mailbox.end_path(inbox), {"end": True})
    session = FakeAgentSession()
    assert serve(root, inbox, output, session) == 0
    assert session.closed
    assert [item["input"] for item in session.history] == ["hi", "again"]
    assert {item["session_id"] for item in session.history} == {"chat-1"}
    assert len({item["run_id"] for item in session.history}) == 2
    request = json.loads((output / "steps/0002/request.json").read_text(encoding="utf-8"))
    assert request["schema"] == "abb.invocation.v1"
    assert request["observation_context"] == {"input_id": "0002"}
    from agentbench.observe.input_artifacts import read_input_artifacts
    record, _ = read_input_artifacts("steps/0002", lambda name: json.loads((output / name).read_text())
                                     if (output / name).is_file() else None)
    assert record == {"input_id": "0002", "payload": "again"}
    assert json.loads((output / "steps/0001/result.json").read_text())["output"] == "reply 1: hi"


def test_worker_rejects_a_turn_file_out_of_order(tmp_path):
    root, inbox = unit(tmp_path), tmp_path / "in"
    mailbox.post(mailbox.turn_path(inbox, 1), mailbox.turn(2, "hi"))
    session = FakeAgentSession()
    with pytest.raises(ValueError, match="Invalid chat turn"):
        serve(root, inbox, tmp_path / "out", session)
    assert session.closed


def test_chat_argv_reuses_the_worker_interpreter(tmp_path):
    root = unit(tmp_path)
    assert host.chat_argv(root) == ["python", "-m", "agentbench.runtime.agentcontainer.chat"]
    (root / "agent.toml").write_text(MANIFEST.replace("agentbench.runtime.agentcontainer.worker", "native"),
                                     encoding="utf-8")
    with pytest.raises(ValueError, match="argv"):
        host.chat_argv(root)


class ContainerSession:
    """Runs the real chat worker loop in a thread over the mounted directories."""

    def __init__(self, root, inputs, output, argv, fail_on=None):
        self.session = FakeAgentSession()
        self.validated = self.closed = False
        session_id = argv[argv.index("--session-id") + 1]
        self.thread = threading.Thread(target=lambda: asyncio.run(worker.serve(
            root, inputs, output, session_id=session_id, session=self.session,
            invoke=fake_invoke(fail_on), publish=lambda path: None, poll=0.01)), daemon=True)
        self.thread.start()
        self.stdout = self.stderr = ""

    @property
    def returncode(self):
        return None if self.thread.is_alive() else 0

    def wait(self, timeout=None):
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise subprocess.TimeoutExpired("chat", timeout)
        return 0

    def trace_checkpoint(self):
        return 0

    def validate_trace(self, checkpoint):
        self.validated = True

    def close(self):
        self.closed = True


def fake_runtime(started, fail_on=None):
    def factory(**options):
        def start(agent, *, invocation, argv):
            inputs, output = invocation
            # The interceptor records model traffic from the container's first call.
            options["trace_sink"].record("interceptor_ready")
            started.append(ContainerSession(agent.path, inputs, output, argv, fail_on))
            return started[-1]
        return SimpleNamespace(invocation_timeout=lambda agent: 10, start=start)
    return factory


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(host, "prepare_agent_source", lambda root, **kwargs: None)
    monkeypatch.setattr("agentbench.trajectory.metadata.capture_target", lambda root: {"schema": "target"})
    monkeypatch.setattr("agentbench.trajectory.atif.attempt.write",
                        lambda directory, **kwargs: {"status": "valid", "path": "trajectory.atif.json", "steps": 4})


def chat(tmp_path, lines, started, fail_on=None):
    agent = SimpleNamespace(agent_id="demo", path=unit(tmp_path))
    answers, written = iter(lines), []

    def read(prompt):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError
    factory = lambda agent, **options: host.ChatSession(
        agent, runtime_factory=fake_runtime(started, fail_on), poll=0.01, **options)
    run = host.run_chat(agent, output=tmp_path / "results", environ={}, read=read,
                        write=written.append, session_factory=factory)
    return run, "\n".join(written)


def test_chat_replies_then_prints_the_saved_record_paths(tmp_path, patched):
    started = []
    run, text = chat(tmp_path, ["hi", "   ", "again", "/exit", "never sent"], started)
    assert "demo: reply 1: hi" in text and "demo: reply 2: again" in text
    assert [item["input"] for item in started[0].session.history] == ["hi", "again"]
    assert started[0].session.closed and started[0].validated and started[0].closed
    directory = tmp_path / "results" / run["run_id"]
    assert len(run["run_id"]) == 8 and all(char in "0123456789abcdef" for char in run["run_id"])
    saved = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    assert saved["status"] == "succeeded" and saved["host_trace_validation"] == "succeeded"
    assert [item["directory"] for item in saved["turns"]] == ["steps/0001", "steps/0002"]
    assert (directory / "request/turns/end.json").is_file()
    assert f"Run directory: {directory}" in text
    assert f"Container stdout/stderr: {directory / 'diagnostics.json'}" in text
    assert f"Run status: {directory / 'run.json'}" in text
    assert f"Turn 0002 (request, result, framework/ACP events): {directory / 'steps' / '0002'}" in text


def test_end_of_input_ends_the_chat_gracefully(tmp_path, patched):
    started = []
    run, _ = chat(tmp_path, ["hi"], started)
    assert run["status"] == "succeeded" and len(run["turns"]) == 1
    assert started[0].session.closed


def test_an_unusable_agent_session_ends_the_chat(tmp_path, patched):
    started = []
    run, text = chat(tmp_path, ["hi", "explode", "after"], started, fail_on="explode")
    assert "[turn failed: failed] boom" in text and "no longer usable" in text
    assert [item["input"] for item in started[0].session.history] == ["hi", "explode"]
    assert run["failed_turns"] == 1 and run["status"] == "succeeded"


def test_chat_without_turns_skips_the_trajectory(tmp_path, patched):
    run, text = chat(tmp_path, ["/quit"], [])
    assert run["atif"]["status"] == "skipped" and run["turns"] == []


def test_chat_command_is_registered():
    from agentbench.cli.features import FEATURES
    assert "chat" in [feature.name for feature in FEATURES]

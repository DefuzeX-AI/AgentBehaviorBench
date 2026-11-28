"""agentbench chat --view: page controller, chat API and trajectory marks."""
import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.observe.chat_view import ChatController
from agentbench.trajectory.atif import marks
from agentbench.trajectory.atif.slim import slim


def document():
    return {"schema_version": "ATIF-v1.8", "session_id": "run-1", "trajectory_id": "root",
            "agent": {"name": "demo", "version": "1"},
            "steps": [{"step_id": 1, "source": "user", "message": "hi",
                       "extra": {"abb": {"evidence": [{"file": "steps/0001/input.json", "line": None}]}}},
                      {"step_id": 2, "source": "agent", "message": "hello",
                       "extra": {"abb": {"evidence": [{"file": "otel/spans.jsonl", "line": 3}]}}}],
            "extra": {"abb": {"source": "acp_otel"}}}


def saved(tmp_path):
    (tmp_path / "trajectory.atif.json").write_text(json.dumps(document()), encoding="utf-8")
    return lambda: json.loads((tmp_path / "trajectory.atif.json").read_text(encoding="utf-8"))


def test_a_mark_is_written_straight_into_the_saved_trajectory(tmp_path):
    pytest.importorskip("harbor")
    read = saved(tmp_path)
    first, digest = marks.add(tmp_path, "root", 2, "  claimed a file it never read  ")
    second, _ = marks.add(tmp_path, "root", 2, "second look")
    stored = read()["steps"][1]["extra"]["abb"]
    assert stored["marks"] == [{"reason": "claimed a file it never read", "created_at": first["created_at"]},
                               {"reason": "second look", "created_at": second["created_at"]}]
    assert stored["evidence"] == [{"file": "otel/spans.jsonl", "line": 3}]
    assert not (tmp_path / "marks.json").exists()
    import hashlib
    assert len(digest) == 64
    # The stored key has an explicit storage rule.
    assert slim(read())["steps"][1]["extra"]["abb"]["marks"][0]["reason"] == "claimed a file it never read"
    digest = marks.remove(tmp_path, "root", 2, first["created_at"])
    assert [m["reason"] for m in read()["steps"][1]["extra"]["abb"]["marks"]] == ["second look"]
    assert digest == hashlib.sha256((tmp_path / "trajectory.atif.json").read_bytes()).hexdigest()
    marks.remove(tmp_path, "root", 2, second["created_at"])
    assert "marks" not in read()["steps"][1]["extra"]["abb"]


def test_marks_reject_unknown_steps_missing_reasons_and_unsaved_trajectories(tmp_path):
    pytest.importorskip("harbor")
    with pytest.raises(FileNotFoundError):
        marks.add(tmp_path, "root", 1, "no file yet")
    read = saved(tmp_path)
    with pytest.raises(KeyError):
        marks.add(tmp_path, "root", 9, "no such step")
    with pytest.raises(KeyError):
        marks.add(tmp_path, "child", 1, "no such trajectory")
    with pytest.raises(ValueError):
        marks.add(tmp_path, "root", 1, "   ")
    with pytest.raises(KeyError):
        marks.remove(tmp_path, "root", 1, "2026-01-01T00:00:00+00:00")
    assert read() == document()


def test_a_mark_on_a_step_without_extra_leaves_it_clean_after_removal(tmp_path):
    pytest.importorskip("harbor")
    base = document()
    del base["steps"][0]["extra"]
    (tmp_path / "trajectory.atif.json").write_text(json.dumps(base), encoding="utf-8")
    mark, _ = marks.add(tmp_path, "root", 1, "greeting only")
    marks.remove(tmp_path, "root", 1, mark["created_at"])
    assert "extra" not in json.loads((tmp_path / "trajectory.atif.json").read_text(encoding="utf-8"))["steps"][0]


class FakeChat:
    """A ChatSession double whose turns finish when the test releases them."""

    def __init__(self, agent, *, output, environ, timeout=None):
        self.output = Path(output)
        self.directory = None
        self.run = None
        self.release = threading.Event()
        self.closed = None

    def start(self):
        self.directory = self.output / "run-1"
        (self.directory / "steps").mkdir(parents=True)
        self.run = {"run_id": "run-1", "status": "running", "turns": []}
        return self.directory

    def send(self, value):
        self.release.wait(5)
        number = len(self.run["turns"]) + 1
        folder = self.directory / "steps" / f"{number:04d}"
        folder.mkdir()
        result = {"status": "succeeded", "output": f"echo {value}"}
        (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (folder / "input.json").write_text(json.dumps({"input_id": f"{number:04d}", "payload": value}), encoding="utf-8")
        self.run["turns"].append({"turn": number, "status": "succeeded"})
        return result

    def close(self, status="succeeded", error=None):
        self.closed = status
        (self.directory / "trajectory.atif.json").write_text(json.dumps(document()), encoding="utf-8")
        (self.directory / "run.json").write_text("{}", encoding="utf-8")
        self.run.update(status=status, atif={"status": "complete", "steps": 2, "sha256": "old"})
        return self.run


def controller(tmp_path, preview=None):
    agent = SimpleNamespace(agent_id="demo", path=tmp_path)
    chat = ChatController(agent, output=tmp_path / "results", environ={}, session_factory=FakeChat,
                          preview=preview or (lambda directory, run: (document(), {"status": "partial"})))
    chat.start()
    return chat


def wait_for(predicate):
    for _ in range(200):
        if predicate():
            return
        threading.Event().wait(0.02)
    raise AssertionError("condition not reached")


def test_controller_answers_one_turn_at_a_time(tmp_path):
    chat = controller(tmp_path)
    assert chat.trajectory()["status"] == "pending"
    chat.submit("hi")
    assert chat.state()["phase"] == "busy"
    with pytest.raises(RuntimeError, match="busy"):
        chat.submit("again")
    with pytest.raises(ValueError):
        controller(tmp_path / "other").submit("  ")
    chat.chat.release.set()
    wait_for(lambda: chat.state()["phase"] == "ready")
    turn = chat.state()["turns"][0]
    assert turn["status"] == "succeeded" and turn["output"] == "echo hi" and turn["answered_at"]
    assert chat.raw(1)["result"]["output"] == "echo hi"
    preview = chat.trajectory()
    assert preview["saved"] is False and preview["status"] == "partial"
    with pytest.raises(RuntimeError, match="chat has ended"):
        chat.mark("root", 2, "too early: the trajectory is not saved yet")


def test_live_preview_refreshes_when_only_late_model_evidence_changes(tmp_path):
    calls = []

    def preview(directory, run):
        calls.append(directory)
        return document(), {"status": "partial"}

    chat = controller(tmp_path, preview)
    chat.chat.release.set()
    chat.submit("delegate")
    wait_for(lambda: chat.state()["phase"] == "ready")
    network = chat.directory / "logs" / "network.jsonl"
    network.parent.mkdir(exist_ok=True)
    network.touch()
    chat.trajectory()
    chat.trajectory()
    assert len(calls) == 1
    network.write_text('{"event":"llm_response"}\n', encoding="utf-8")
    chat.trajectory()
    assert len(calls) == 2


def test_after_the_chat_ends_marks_edit_the_saved_trajectory(tmp_path):
    pytest.importorskip("harbor")
    chat = controller(tmp_path)
    chat.chat.release.set()
    chat.submit("hi")
    wait_for(lambda: chat.state()["phase"] == "ready")
    chat.end(wait=True)
    state = chat.state()
    assert state["phase"] == "ended" and chat.chat.closed == "succeeded"
    # The page names the trajectory and the run directory; it lists no other record.
    assert state["trajectory_path"] == str(chat.directory / "trajectory.atif.json") and "records" not in state
    assert state["directory"] == str(chat.directory)
    saved = chat.trajectory()
    assert saved["saved"] is True
    mark = chat.mark("root", 1, "greeting only")
    stored = json.loads((chat.directory / "trajectory.atif.json").read_text(encoding="utf-8"))
    assert stored["steps"][0]["extra"]["abb"]["marks"] == [mark]
    import hashlib
    run = json.loads((chat.directory / "run.json").read_text(encoding="utf-8"))
    assert run["atif"]["sha256"] == hashlib.sha256((chat.directory / "trajectory.atif.json").read_bytes()).hexdigest()
    assert chat.trajectory()["document"]["steps"][0]["extra"]["abb"]["marks"] == [mark]
    chat.unmark("root", 1, mark["created_at"])
    stored = json.loads((chat.directory / "trajectory.atif.json").read_text(encoding="utf-8"))
    assert "marks" not in stored["steps"][0]["extra"]["abb"]
    assert not (chat.directory / "marks.json").exists()


def test_ending_while_the_agent_answers_records_an_interruption(tmp_path):
    chat = controller(tmp_path)
    chat.submit("hi")
    chat.end(wait=True)
    assert chat.chat.closed == "interrupted"
    chat.chat.release.set()


@pytest.fixture
def server(tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    from agentbench.cli.viewer import chat as viewer
    from agentbench.cli.viewer.server import ViewerHTTPServer
    monkeypatch.setattr(viewer, "WEB_ROOT", web)
    chat = controller(tmp_path)
    chat.chat.release.set()
    instance = ViewerHTTPServer(("127.0.0.1", 0), viewer.build_chat_handler(chat, "secret-token"))
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    yield instance.server_port, chat
    instance.shutdown()
    instance.server_close()


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = json.dumps(body).encode() if body is not None else None
    base = {"Content-Type": "application/json", **({"Content-Length": str(len(data))} if data else {})}
    connection.request(method, path, body=data, headers={**base, **(headers or {})})
    response = connection.getresponse()
    payload = response.read().decode("utf-8")
    connection.close()
    return response.status, payload


def test_chat_api_serves_the_page_and_requires_the_token_for_commands(server):
    port, chat = server
    origin = {"Origin": f"http://127.0.0.1:{port}"}
    status, html = request(port, "GET", "/chat/")
    assert status == 200 and 'name="abb-chat-api" content="/api/chat"' in html and "secret-token" in html
    status, body = request(port, "GET", "/api/chat/state")
    assert status == 200 and json.loads(body)["phase"] == "ready"
    assert request(port, "POST", "/api/chat/turns", {"input": "hi"}, origin)[0] == 403
    assert request(port, "POST", "/api/chat/turns", {"input": "hi"},
                   {"Origin": "http://evil.example", "X-ABB-Control-Token": "secret-token"})[0] == 403
    status, body = request(port, "POST", "/api/chat/turns", {"input": "hi"}, {**origin, "X-ABB-Control-Token": "secret-token"})
    assert status == 202 and json.loads(body)["turn"] == 1
    wait_for(lambda: chat.state()["phase"] == "ready")
    status, body = request(port, "GET", "/api/chat/turns/1/raw")
    assert status == 200 and json.loads(body)["result"]["output"] == "echo hi"
    assert request(port, "GET", "/api/chat/turns/9/raw")[0] == 404
    command = {**origin, "X-ABB-Control-Token": "secret-token"}
    # Marks edit the saved trajectory, which exists only after the chat ends.
    assert request(port, "POST", "/api/chat/marks", {"trajectory_id": "root", "step_id": 1, "reason": "x"}, command)[0] == 409
    status, _ = request(port, "POST", "/api/chat/end", {}, command)
    assert status == 202
    chat.ended.wait(5)
    assert json.loads(request(port, "GET", "/api/chat/state")[1])["phase"] == "ended"
    pytest.importorskip("harbor")
    assert request(port, "POST", "/api/chat/marks", {"trajectory_id": "root", "step_id": 1, "reason": ""}, command)[0] == 400
    assert request(port, "POST", "/api/chat/marks", {"trajectory_id": "root", "step_id": 99, "reason": "x"}, command)[0] == 404
    status, body = request(port, "POST", "/api/chat/marks", {"trajectory_id": "root", "step_id": 1, "reason": "greeting"}, command)
    assert status == 201
    created = json.loads(body)["created_at"]
    stored = json.loads((chat.directory / "trajectory.atif.json").read_text(encoding="utf-8"))
    assert stored["steps"][0]["extra"]["abb"]["marks"][0]["reason"] == "greeting"
    assert request(port, "POST", "/api/chat/marks/delete",
                   {"trajectory_id": "root", "step_id": 1, "created_at": created}, command)[0] == 200


def test_chat_view_flag_is_available():
    import argparse
    from agentbench.cli.features.chat import configure_parser
    parser = argparse.ArgumentParser()
    configure_parser(parser)
    args = parser.parse_args(["openclaw", "--view", "--port", "0"])
    assert args.view and args.port == 0

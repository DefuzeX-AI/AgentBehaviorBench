"""A finished attempt carries trajectory.atif.json beside its evidence."""
import hashlib
import json

import pytest

from tests.atif_fixtures import fixture, save
from agentbench.trajectory.atif import SCHEMA_VERSION, attempt
from agentbench.trajectory.atif.provenance import snapshot
from tests.test_sdk_defaults import inprocess_worker_permissions  # noqa: F401 - autouse fixture
from tests.test_sdk_execution import fake_services, make_runner, source_agent


def recording_services():
    """Fake runtime whose container leaves one answered Input in the attempt."""
    services, _ = fake_services()
    create = services.create_docker_runtime

    def create_runtime(**options):
        runtime = create(**options)
        start = runtime.start

        def recorded(agent, *, invocation, **kwargs):
            session = start(agent, invocation=invocation, **kwargs)
            save(invocation[1] / "steps/0001/input.json", {"input_id": "first", "payload": "hello"})
            save(invocation[1] / "steps/0001/result.json", {"status": "succeeded", "output": "hi there"})
            return session

        runtime.start = recorded
        return runtime

    services.create_docker_runtime = create_runtime
    return services


def test_write_saves_the_document_beside_unchanged_evidence(tmp_path):
    fixture(tmp_path, "steps")
    before = snapshot(tmp_path)
    status = attempt.write(tmp_path)
    raw = (tmp_path / attempt.FILENAME).read_bytes()
    document = json.loads(raw)
    assert status == {"status": "complete", "path": "trajectory.atif.json",
                      "sha256": hashlib.sha256(raw).hexdigest(), "steps": len(document["steps"]), "issues": 0}
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["steps"][0]["source"] == "user" and document["steps"][0]["message"] == "你好 ¡España!"
    assert snapshot(tmp_path) == before


def test_in_memory_run_status_stands_in_for_an_unfinished_run_json(tmp_path):
    fixture(tmp_path, "steps", finished=False)
    refused = attempt.write(tmp_path)
    assert refused["status"] == "failed" and "not known to be finished" in refused["error"]
    assert not (tmp_path / attempt.FILENAME).exists()
    run = {"run_id": "run-a", "agent_id": "fixture", "status": "succeeded"}
    assert attempt.write(tmp_path, run=run)["status"] == "complete"
    document = json.loads((tmp_path / attempt.FILENAME).read_text(encoding="utf-8"))
    assert document["session_id"] == "run-a"
    assert json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))["status"] == "running"


def test_adapters_are_the_ones_frozen_from_the_agent_unit(tmp_path):
    fixture(tmp_path, "steps")
    assert attempt.declared_adapters(tmp_path) == ()
    target = {"architecture": {"source_revision": "frozen-revision"}, "runtime": {"atif": {"adapters": ["deepagents"]}}}
    save(tmp_path / "request/target.json", target)
    assert attempt.declared_adapters(tmp_path) == ("deepagents",)
    assert attempt.write(tmp_path)["status"] == "complete"
    target["runtime"]["atif"]["adapters"] = ["no-such-adapter"]
    save(tmp_path / "request/target.json", target)
    unknown = attempt.write(tmp_path)
    assert unknown["status"] == "failed" and "Unknown delegation adapters" in unknown["error"]
    target["runtime"]["atif"]["adapters"] = "deepagents"
    save(tmp_path / "request/target.json", target)
    assert attempt.write(tmp_path)["error"] == "[atif] adapters must be a list of adapter names"


def test_agent_unit_declaration_is_frozen_into_the_target(tmp_path):
    from agentbench.trajectory.metadata import capture_target
    (tmp_path / "agent.toml").write_text('agent_id = "unit"\nframework = "acp"\n\n[atif]\nadapters = ["openclaw"]\n',
                                         encoding="utf-8")
    assert capture_target(tmp_path)["runtime"]["atif"] == {"adapters": ["openclaw"]}


def test_missing_harbor_is_reported_as_unavailable(tmp_path, monkeypatch):
    import agentbench.trajectory.atif.export as export
    fixture(tmp_path, "steps")

    def missing(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'harbor'", name="harbor")

    monkeypatch.setattr(export, "build_export", missing)
    status = attempt.write(tmp_path)
    assert status["status"] == "unavailable" and attempt.INSTALL_HINT in status["error"]
    assert not (tmp_path / attempt.FILENAME).exists()


def test_execution_writes_the_document_and_records_its_status(tmp_path):
    agent = source_agent(tmp_path)
    runner = make_runner(tmp_path, recording_services())
    case, = runner.prepare_cases(agent)
    assert runner.run_case(agent, case).passed
    status = json.loads((runner.directory / "run.json").read_text(encoding="utf-8"))
    assert status["atif"]["path"] == "trajectory.atif.json"
    assert status["atif"]["status"] in ("complete", "partial") and status["atif"]["steps"] == 2
    raw = (runner.directory / "trajectory.atif.json").read_bytes()
    assert status["atif"]["sha256"] == hashlib.sha256(raw).hexdigest()
    document = json.loads(raw)
    assert document["schema_version"] == SCHEMA_VERSION and document["agent"]["name"] == agent.agent_id
    assert [(step["source"], step["message"]) for step in document["steps"]] == [("user", "hello"), ("agent", "hi there")]


def test_conversion_failure_never_changes_the_execution_outcome(tmp_path, monkeypatch):
    import agentbench.trajectory.atif.export as export
    monkeypatch.setattr(export, "build_export", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("converter exploded")))
    agent = source_agent(tmp_path)
    runner = make_runner(tmp_path, recording_services())
    case, = runner.prepare_cases(agent)
    assert runner.run_case(agent, case).passed
    status = json.loads((runner.directory / "run.json").read_text(encoding="utf-8"))
    assert status["status"] == "succeeded"
    assert status["atif"] == {"status": "failed", "path": "trajectory.atif.json",
                              "error_type": "RuntimeError", "error": "converter exploded"}
    assert not (runner.directory / "trajectory.atif.json").exists()

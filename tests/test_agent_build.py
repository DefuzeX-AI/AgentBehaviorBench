"""Sequential writes, retries, checkpoints and interruption behavior."""
import copy
import json
from pathlib import Path
import pytest
from agentbench.harness.registry import load_registry
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.records import records_directory
from tests.agent_build_fixtures import source, plan, Client, build, write, REQUIREMENT, FILES


def test_each_file_is_saved_before_requesting_the_next(source, plan):
    unit = source.directory
    messages = []
    def check(payload):
        name = payload.get("target_path")
        if name == "Dockerfile":
            assert (unit / "agent.toml").is_file()
            assert (unit / "bindings/bridge.py").is_file()
            assert not (unit / "Dockerfile").exists()
            assert "agent.toml" in payload["completed_files"]
        if name == "requirement.md":
            assert (unit / "Dockerfile").is_file() and (unit / ".dockerignore").is_file()
    client = Client(plan, callback=check)
    result = build(source, plan, client=client, output_fn=messages.append)
    assert result.status == "generated"
    assert [item.get("target_path") for item in client.requests] == [None, "agent.toml", "bindings/bridge.py", "Dockerfile", "requirement.md"]
    assert not (unit / "evaluation").exists()
    assert not (unit / "agent.toml").stat().st_mode & 0o111
    assert (unit / "agent.toml").stat().st_mode & 0o444 == 0o444
    record = load_registry(unit.parents[1] / "registry.toml").find("my-agent")
    assert record.status == "adapting"
    assert record.requirement_path.read_text() == REQUIREMENT
    assert [line.split(":", 1)[0] for line in messages if ": saved " in line] == [
        "[1/5] agent.toml", "[2/5] bindings/bridge.py", "[3/5] Dockerfile", "[4/5] .dockerignore", "[5/5] requirement.md"]


def test_failure_preserves_completed_files_and_retry_resumes_without_replanning(source, plan):
    broken = {**FILES, "Dockerfile": "FROM python:3.11\nRUN pip install ./agent\nCOPY agent/ ./agent/\nUSER agent"}
    first = Client(plan, files=broken)
    with pytest.raises(BuildError, match="before installing"):
        build(source, plan, client=first)
    manifest = source.directory / "agent.toml"
    before = manifest.read_bytes(), manifest.stat().st_mtime_ns
    assert not (source.directory / "Dockerfile").exists()
    assert not (source.directory.parents[1] / "registry.toml").exists()
    second = Client(plan)
    assert build(source, plan, client=second).status == "generated"
    assert [item.get("target_path") for item in second.requests] == ["Dockerfile", "requirement.md"]
    assert (manifest.read_bytes(), manifest.stat().st_mtime_ns) == before


def test_completed_run_reuses_every_file_without_model_calls(source, plan):
    build(source, plan)
    def unexpected(payload):
        pytest.fail("completed files must not trigger another paid request")
    client = Client(plan, callback=unexpected)
    assert build(source, plan, client=client).status == "generated"
    assert client.requests == []


def test_keyboard_interrupt_keeps_checkpoint_and_releases_lock(source, plan):
    def interrupt(payload):
        if payload.get("target_path") == "Dockerfile":
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        build(source, plan, client=Client(plan, callback=interrupt))
    assert (source.directory / "agent.toml").is_file()
    root = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    records = [json.loads(path.read_text()) for path in root.glob("*/build-result.json")]
    assert records[-1]["status"] == "interrupted"
    assert records[-1]["completed_files"] == ["agent.toml", "bindings/bridge.py"]
    assert build(source, plan).status == "generated"


def test_only_the_current_file_receives_validation_feedback(source, plan):
    calls = 0
    def invalid_first(payload):
        nonlocal calls
        if payload.get("target_path") == "requirement.md":
            calls += 1
            if calls == 1:
                return {"status": "complete", "summary": "Malformed profile", "evidence": plan["evidence"],
                        "missing_information": [], "path": "requirement.md", "content": "legacy text"}
            assert payload["previous_response"]["path"] == "requirement.md"
            assert "validation_error" in payload
            assert (source.directory / "agent.toml").is_file()
    client = Client(plan, callback=invalid_first)
    result = build(source, plan, client=client)
    assert result.status == "generated" and calls == 2
    assert [item.get("target_path") for item in client.requests].count("agent.toml") == 1
    assert len(list((result.attempt / "steps/05-requirement.md").glob("response-*.json"))) == 2


def test_invalid_requirement_does_not_roll_back_earlier_files(source, plan):
    with pytest.raises(BuildError, match="KUMA requirement.md"):
        build(source, plan, client=Client(plan, files={**FILES, "requirement.md": "legacy text"}))
    assert (source.directory / "agent.toml").is_file()
    assert (source.directory / "Dockerfile").is_file()
    assert not (source.directory / "requirement.md").exists()
    assert not (source.directory.parents[1] / "registry.toml").exists()


def test_manual_files_are_validated_and_never_overwritten(source, plan):
    manual = FILES["agent.toml"] + "\n# Hand-written configuration\n"
    write(source.directory, "agent.toml", manual)
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert "agent.toml" not in [item.get("target_path") for item in client.requests]
    assert (source.directory / "agent.toml").read_text() == manual


def test_invalid_manual_file_pauses_without_replacing_it(source, plan):
    write(source.directory, "agent.toml", "manual unfinished configuration")
    result = build(source, plan)
    assert result.status == "conflict"
    assert "agent.toml" in result.messages[0]
    assert (source.directory / "agent.toml").read_text() == "manual unfinished configuration"
    assert not (source.directory / "Dockerfile").exists()


@pytest.mark.parametrize("status", ["needs_input", "unsupported"])
def test_incomplete_plan_does_not_start_file_generation(source, plan, status):
    plan.update(status=status, missing_information=["Which graph should be used?"], bindings=[])
    client = Client(plan)
    result = build(source, plan, client=client)
    assert result.status == status and len(client.requests) == 1
    assert not (source.directory / "agent.toml").exists()


def test_question_during_a_file_stage_keeps_earlier_files(source, plan):
    def question(payload):
        if payload.get("target_path") == "Dockerfile":
            return {"status": "needs_input", "summary": "Need an image", "evidence": plan["evidence"],
                    "missing_information": ["Which approved base image?"], "path": "Dockerfile", "content": ""}
    result = build(source, plan, client=Client(plan, callback=question))
    assert result.status == "needs_input"
    assert (source.directory / "agent.toml").is_file()
    assert not (source.directory / "Dockerfile").exists()


def test_input_schema_is_saved_before_sdk_requirement(source, plan):
    plan["needs_input_schema"] = True
    files = {**FILES, "evaluation/input-schema.json": '{"type":"object","required":["topic"],"properties":{"topic":{"type":"string"}}}',
             "requirement.md": REQUIREMENT.replace("input_type: text", "input_type: structured\ninput_schema: evaluation/input-schema.json")}
    def check(payload):
        if payload.get("target_path") == "requirement.md":
            assert (source.directory / "evaluation/input-schema.json").is_file()
    client = Client(plan, files=files, callback=check)
    assert build(source, plan, client=client).status == "generated"
    assert [item.get("target_path") for item in client.requests][-2:] == ["evaluation/input-schema.json", "requirement.md"]


def test_required_binding_is_created_before_dockerfile_without_importing_it(source, plan):
    files = {**FILES,
             "bindings/bridge.py": 'raise AssertionError("never import")\ndef create_graph(): pass\n'}
    def check(payload):
        if payload.get("target_path") == "Dockerfile":
            assert (source.directory / "bindings/bridge.py").is_file()
    client = Client(plan, files=files, callback=check)
    assert build(source, plan, client=client).status == "generated"
    assert [item.get("target_path") for item in client.requests][:4] == [None, "agent.toml", "bindings/bridge.py", "Dockerfile"]

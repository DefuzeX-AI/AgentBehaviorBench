"""Actionable feedback through the real onboarding request and repair path."""
import io
import json
from types import SimpleNamespace

import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.records import records_directory
from agentbench.onboarding.build_agent_env.common.responses import validate_response
from tests.agent_build_fixtures import source, plan, Client, build
from tests.test_agent_build_client import client


def wire(content, finish="stop", **extra):
    return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish,
        "message": {"content": content}}], **extra}).encode())


@pytest.mark.parametrize("stage", ["plan", "file", "review"])
@pytest.mark.parametrize("failure", ["enum", "json"])
def test_repairs_failing_response_with_specific_feedback(source, plan, stage, failure):
    instance, fixture, requests, selected = client(), Client(plan), [], []
    def open_request(request, **kwargs):
        payload = json.loads(json.loads(request.data)["messages"][1]["content"])
        requests.append(payload)
        result = fixture.generate(payload, prompt="", schema={})
        is_review = payload.get("response_kind") == "configuration_review"
        matches = (stage == "plan" and "target_path" not in payload or
                   stage == "file" and payload.get("target_path") == "requirement.md" and not is_review or
                   stage == "review" and payload.get("target_path") == "requirement.md" and is_review)
        if matches:
            selected.append(payload)
            if len(selected) == 1:
                if failure == "json":
                    return wire(json.dumps(result)[:-1] + ",}")
                result["status"] = "ok"
            else:
                error = payload["validation_error"]
                if failure == "enum":
                    assert "$.status" in error and "complete" in error
                    assert payload["previous_response"]["status"] == "ok"
                else:
                    assert "line" in error and "column" in error
                    assert payload["previous_content"].endswith(",}")
        return wire(json.dumps(result))
    instance.opener = SimpleNamespace(open=open_request)
    result = build(source, plan, client=instance)
    assert result.status == "generated" and len(selected) == 2
    if stage == "review":
        assert sum(p.get("target_path") == "requirement.md" and
                   p.get("response_kind") != "configuration_review" for p in requests) == 1
    records = [json.loads(p.read_text()) for p in result.attempt.rglob("*validation-*.json")]
    assert any(("$.status" in r["error"] if failure == "enum" else "column" in r["error"]) for r in records)


def test_schema_feedback_is_specific_and_does_not_dump_content():
    schema = {"type": "object", "required": ["path"], "properties": {
        "facts": {"anyOf": [{"type": "object", "properties": {
            "adapter": {"type": "object", "properties": {"config": {"type": "string"}}}}},
            {"type": "null"}]}}}
    response = {"facts": {"adapter": {"config": None}, "content": "PRIVATE_SOURCE" * 1000}}
    session = SimpleNamespace(environ={}, context={"files": []})
    with pytest.raises(BuildError) as error:
        validate_response(response, schema, session)
    text = str(error.value)
    assert "$.path" in text and "required" in text
    assert "$.facts.adapter.config" in text and "string" in text and "null" in text
    assert "PRIVATE_SOURCE" not in text and len(text) <= 2048


@pytest.mark.parametrize("content", ['{"status":"complete",}', r'{"content":"bad\q"}', '[]'])
def test_decode_diagnostics_identify_model_content(content):
    with pytest.raises(BuildError) as error:
        client()._decode(wire(content).getvalue())
    text = str(error.value)
    assert "model content" in text
    assert ("line" in text and "column" in text) if content != '[]' else "object" in text


def test_truncation_metadata_reaches_saved_build_result(source, plan):
    instance = client()
    instance.opener = SimpleNamespace(open=lambda *a, **k: wire("", "length", usage={
        "completion_tokens": 32000, "completion_tokens_details": {"reasoning_tokens": 31997}}))
    with pytest.raises(BuildError, match="finish_reason=length"):
        build(source, plan, client=instance)
    root = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    result = json.loads(next(root.glob("*/build-result.json")).read_text())
    metadata = result["diagnostics"]
    assert metadata["finish_reason"] == "length"
    assert metadata["completion_tokens"] == 32000 and metadata["reasoning_tokens"] == 31997
    assert metadata["content_chars"] == 0


@pytest.mark.parametrize("escaped", [False, True])
def test_malformed_json_with_credentials_is_not_saved_or_retried(source, plan, escaped):
    instance, calls = client(), []
    secret = "test-credential-never-log"
    value = ''.join('\\u%04x' % ord(c) for c in secret) if escaped else secret
    def open_request(*args, **kwargs):
        calls.append(1)
        return wire('{"content":"' + value + '",}')
    instance.opener = SimpleNamespace(open=open_request)
    with pytest.raises(BuildError):
        build(source, plan, client=instance)
    assert len(calls) == 1
    root = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    for path in root.rglob("*.json"):
        assert secret not in path.read_text() and value not in path.read_text()


@pytest.mark.parametrize("repairs", [0, 1, 2])
def test_decode_failures_obey_configured_budget(source, plan, tmp_path, repairs):
    instance, calls = client(), []
    settings = tmp_path / "build.toml"
    settings.write_text(f"[build]\nrepair_attempts = {repairs}\n")
    def open_request(*args, **kwargs):
        calls.append(1)
        return wire('{"status":"complete",}')
    instance.opener = SimpleNamespace(open=open_request)
    with pytest.raises(BuildError, match="column"):
        build(source, plan, client=instance, settings_path=settings)
    assert len(calls) == repairs + 1
    assert not (source.directory / "agent.toml").exists()


def test_file_and_review_share_repair_budget(source, plan):
    instance, fixture, selected = client(), Client(plan), []
    def open_request(request, **kwargs):
        payload = json.loads(json.loads(request.data)["messages"][1]["content"])
        result = fixture.generate(payload, prompt="", schema={})
        if payload.get("target_path") == "requirement.md":
            selected.append(payload)
            if len(selected) == 1:
                return wire(json.dumps(result)[:-1] + ",}")
            if payload.get("response_kind") == "configuration_review":
                result["status"] = "invalid"
        return wire(json.dumps(result))
    instance.opener = SimpleNamespace(open=open_request)
    with pytest.raises(BuildError, match=r"\$\.status"):
        build(source, plan, client=instance)
    assert len(selected) == 3  # Initial file + one correction + initial review.
    assert (source.directory / "agent.toml").exists()
    assert not (source.directory / "requirement.md").exists()
    assert not (source.directory.parents[1] / "registry.toml").exists()


@pytest.mark.parametrize("failure", ["envelope", "transport", "truncation"])
def test_review_provider_failure_does_not_regenerate_candidate(source, plan, failure):
    from urllib.error import URLError
    instance, fixture, selected = client(retries=0), Client(plan), []
    def open_request(request, **kwargs):
        payload = json.loads(json.loads(request.data)["messages"][1]["content"])
        result = fixture.generate(payload, prompt="", schema={})
        if payload.get("target_path") == "requirement.md":
            selected.append(payload)
            if payload.get("response_kind") == "configuration_review":
                if failure == "transport":
                    raise URLError("private transport detail")
                if failure == "envelope":
                    return io.BytesIO(b"{}")
                return wire("", "length")
        return wire(json.dumps(result))
    instance.opener = SimpleNamespace(open=open_request)
    with pytest.raises(BuildError):
        build(source, plan, client=instance)
    assert len(selected) == 2
    assert not (source.directory / "requirement.md").exists()


def test_provider_metadata_does_not_retain_arbitrary_provider_fields():
    from agentbench.onboarding.build_agent_env.openrouter_provider.response_metadata import response_metadata
    metadata = response_metadata({"choices": [{
        "finish_reason": "PRIVATE_SOURCE", "message": {"content": "PRIVATE_SOURCE"}}],
        "usage": {"completion_tokens": "PRIVATE_SOURCE",
                  "completion_tokens_details": {"reasoning_tokens": 7},
                  "provider_debug": "PRIVATE_SOURCE"}, "error": "PRIVATE_SOURCE"})
    assert metadata == {"finish_reason": "unknown", "content_chars": 14,
                        "content_bytes": 14, "reasoning_tokens": 7}


def test_schema_diagnostics_follow_arbitrary_stage_fields():
    schema = {"type": "object", "properties": {
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "priority": {"enum": ["low", "high"]}}}}}}
    session = SimpleNamespace(environ={}, context={"files": []})
    with pytest.raises(BuildError) as error:
        validate_response({"tasks": [{"priority": "PRIVATE_SOURCE"}]}, schema, session)
    assert "$.tasks[0].priority" in str(error.value)
    assert '"low", "high"' in str(error.value)
    assert "PRIVATE_SOURCE" not in str(error.value)


def test_pattern_diagnostic_uses_stage_schema_constraint():
    schema = {"type": "object", "properties": {
        "artifact_name": {"type": "string", "pattern": "^[a-z]+[.]txt$"}}}
    session = SimpleNamespace(environ={}, context={"files": []})
    with pytest.raises(BuildError) as error:
        validate_response({"artifact_name": "PRIVATE_SOURCE"}, schema, session)
    text = str(error.value)
    assert "$.artifact_name" in text and "^[a-z]+[.]txt$" in text
    assert "PRIVATE_SOURCE" not in text

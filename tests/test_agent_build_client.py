"""OpenRouter wire contract, retry policy and credential-safe diagnostics."""

import io
from pathlib import Path
import json
from dataclasses import replace
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from agentbench.onboarding.build_agent_env.openrouter_provider.client import OpenRouterClient
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import BuildError, load_settings


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "agentbench/onboarding/build_agent_env/openrouter_provider/assets/file-response.schema.json"


def generate(instance, payload):
    return instance.generate(payload, prompt="Create the requested file.", schema=json.loads(SCHEMA_PATH.read_text()))


def client(**overrides):
    return OpenRouterClient(replace(load_settings(), **overrides), {
        "OPENROUTER_MODEL": "vendor/test-model", "OPENROUTER_API_KEY": "test-credential-never-log"})


def response(plan=None, finish_reason="stop"):
    return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish_reason,
                                              "message": {"content": json.dumps(plan or {})}}]}).encode())


def test_request_uses_strict_schema_and_keeps_key_out_of_messages():
    instance = client()
    observed = []
    def open_request(request, **kwargs):
        observed.append(request)
        return response({"status": "needs_input"})
    instance.opener = SimpleNamespace(open=open_request)
    assert generate(instance, {"context": {"files": [{"path": "langgraph.json"}]}}) == {"status": "needs_input"}
    request = observed[0]
    assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
    body = json.loads(request.data)
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["properties"]["evidence"]["items"]["enum"] == ["langgraph.json"]
    assert body["provider"]["require_parameters"] is True
    assert "test-credential-never-log" not in request.data.decode()
    assert request.get_header("Authorization") == "Bearer test-credential-never-log"


@pytest.mark.parametrize("status,expected_calls", [(401, 1), (400, 1), (429, 3), (503, 3)])
def test_only_transient_errors_are_retried_and_response_bodies_are_not_logged(monkeypatch, status, expected_calls):
    instance, calls = client(retries=2), []
    monkeypatch.setattr("agentbench.onboarding.build_agent_env.openrouter_provider.client.time.sleep", lambda seconds: None)
    def fail(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://example.invalid", status, "private error text", {},
                        io.BytesIO(b"test-credential-never-log"))
    instance.opener = SimpleNamespace(open=fail)
    with pytest.raises(BuildError) as error:
        generate(instance, {})
    assert len(calls) == expected_calls
    assert str(status) in str(error.value)
    assert "credential" not in str(error.value) and "private" not in str(error.value)


@pytest.mark.parametrize("raw", [b"garbage", b"{}", b'{"choices": []}'])
def test_invalid_response_has_sanitized_error(raw):
    with pytest.raises(BuildError, match="invalid structured"):
        client()._decode(raw)


def test_truncated_model_output_is_not_saved_or_retried():
    with pytest.raises(BuildError, match="did not finish"):
        client()._decode(response(finish_reason="length").getvalue())
    with pytest.raises(BuildError, match="exceeds"):
        client(max_response_bytes=1)._decode(b"{}")


def test_model_selection_does_not_fallback_silently():
    env = {"OPENROUTER_MODEL": "run/model", "OPENROUTER_BUILD_MODEL": "build/model",
           "OPENROUTER_API_KEY": "test-only"}
    assert OpenRouterClient(load_settings(), env).target.model == "build/model"
    assert OpenRouterClient(load_settings(), env, model="explicit/model").target.model == "explicit/model"


def test_client_refuses_base_url_credentials():
    with pytest.raises(BuildError, match="credentials"):
        OpenRouterClient(load_settings(), {"OPENROUTER_MODEL": "v/m", "OPENROUTER_API_KEY": "test",
                                          "OPENROUTER_BASE_URL": "https://user:pass@example.test/api"})


@pytest.mark.parametrize("dockerfile,message", [
    ("FROM python:3.11\nRUN pip install ./agent\nCOPY agent/ ./agent/", "before installing"),
    ("FROM python:3.11\nRUN pip install langgraph>=1.0,<2", "Quote pip"),
])
def test_actual_model_dockerfile_failures_are_rejected(dockerfile, message):
    from agentbench.onboarding.build_agent_env.build_dockerfile.validation import validate_dockerfile
    with pytest.raises(BuildError, match=message):
        validate_dockerfile(dockerfile)


def test_package_install_after_copy_with_quoted_bounds_is_valid():
    from agentbench.onboarding.build_agent_env.build_dockerfile.validation import validate_dockerfile
    validate_dockerfile("FROM python:3.11\nCOPY agent/ ./agent/\n"
                        "RUN python -m pip install ./agent 'opentelemetry-sdk>=1.30,<2'\nUSER agent\n")

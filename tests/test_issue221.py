"""Onboarding must distinguish truncation from other provider stop reasons."""
import json
import io
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agentbench.onboarding.build_agent_env.openrouter_provider.client import OpenRouterClient
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import BuildError, load_settings


@pytest.mark.parametrize("reason", ["length", "content_filter", "secret-provider-text"])
def test_incomplete_build_diagnostics_are_actionable_and_sanitized(reason):
    client = OpenRouterClient(replace(load_settings(), max_output_tokens=12000), {
        "OPENROUTER_MODEL": "test/model", "OPENROUTER_API_KEY": "secret-provider-text"})
    response = {"choices": [{"finish_reason": reason,
                             "message": {"content": "{}"}}],
                "usage": {"completion_tokens": 12000,
                          "completion_tokens_details": {"reasoning_tokens": 11900}}}
    with pytest.raises(BuildError) as error:
        client._decode(json.dumps(response).encode())
    message = str(error.value)
    assert "secret-provider-text" not in message
    assert "completion_tokens=12000" in message
    assert "reasoning_tokens=11900" in message
    assert ("--build-settings" in message) == (reason == "length")


@pytest.mark.parametrize("thinking", ["", "enabled", "disabled"])
def test_thinking_toggle_is_explicit_and_preserves_strict_schema(thinking):
    from tests.test_agent_build_client import generate
    client = OpenRouterClient(replace(load_settings(), thinking=thinking), {
        "OPENROUTER_MODEL": "test/model", "OPENROUTER_API_KEY": "test-key"})
    bodies = []
    def reply(request, **kwargs):
        bodies.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop",
                                                   "message": {"content": "{}"}}]}).encode())
    client.opener = SimpleNamespace(open=reply)
    generate(client, {})
    assert bodies[0].get("thinking") == ({"type": thinking} if thinking else None)
    assert bodies[0]["response_format"]["json_schema"]["strict"] is True


@pytest.mark.parametrize("value", ['"bad"', 'true', '123', '{}', '[]'])
def test_invalid_thinking_setting_is_rejected(tmp_path, value):
    path = tmp_path / "build.toml"
    path.write_text(f"[build]\nthinking = {value}\n")
    with pytest.raises(BuildError, match="build.thinking"):
        load_settings(path)


def test_secret_content_keeps_upstream_rejection_before_finish_diagnostics():
    client = OpenRouterClient(load_settings(), {
        "OPENROUTER_MODEL": "test/model", "OPENROUTER_API_KEY": "secret-provider-text"})
    response = {"choices": [{"finish_reason": "length",
                             "message": {"content": "secret-provider-text"}}]}
    with pytest.raises(BuildError, match="contains a credential") as error:
        client._decode(json.dumps(response).encode())
    assert "secret-provider-text" not in str(error.value)

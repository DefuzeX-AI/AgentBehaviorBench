"""Boundaries for the outer fast-agent launcher; no native source is imported."""
import importlib.util
from pathlib import Path

import pytest
import yaml


PATH = Path(__file__).resolve().parents[1] / "resources/agents/86-fast-agent/bootstrap/launch.py"
SPEC = importlib.util.spec_from_file_location("fast_agent_abb_launch", PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


def settings(**overrides):
    return {"ABB_AGENT_MODEL_API_KEY": "test-secret-not-a-real-key",
            "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/prefix/v1",
            "ABB_AGENT_MODEL": "organization/model", **overrides}


@pytest.mark.parametrize("value", ["http://provider.example", "https://user:secret@provider.example",
                                 "https://provider.example?key=secret", ""])
def test_invalid_endpoint_fails_before_native_launch(tmp_path, value):
    with pytest.raises(ValueError) as error:
        launch.prepare(settings(ABB_AGENT_MODEL_BASE_URL=value), tmp_path)
    assert "secret" not in str(error.value)


def test_provider_agnostic_selection_keeps_permissions_and_secrets_in_environment(tmp_path):
    env = settings()
    before = env.copy()
    command, child = launch.prepare(env, tmp_path)
    assert env == before
    assert command[command.index("--model") + 1] == "generic.organization/model"
    assert "--shell" in command
    assert "--no-home" not in command and "--no-permissions" not in command
    assert child["ABB_AGENT_MODEL_API_KEY"] == env["ABB_AGENT_MODEL_API_KEY"]
    assert env["ABB_AGENT_MODEL_API_KEY"] not in " ".join(command) + launch.CONFIG
    parsed = yaml.safe_load(launch.CONFIG)
    assert parsed["generic"]["api_key"] == "${ABB_AGENT_MODEL_API_KEY}"
    assert child["HOME"] == str(tmp_path)


def test_missing_model_does_not_fall_back_to_another_provider(tmp_path):
    env = settings()
    del env["ABB_AGENT_MODEL"]
    with pytest.raises(ValueError, match="ABB_AGENT_MODEL is required"):
        launch.prepare(env, tmp_path)

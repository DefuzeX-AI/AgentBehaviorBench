"""Boundary checks for the outer Coddy launcher; no Agent or network is started."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "resources/agents/70-coddy/bootstrap/launch.py"
SPEC = importlib.util.spec_from_file_location("coddy_abb_launcher", PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


def settings(**overrides):
    return {"ABB_AGENT_MODEL_API_KEY": "test-key-not-a-real-credential",
            "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/prefix/v1",
            "ABB_AGENT_MODEL": "organization/model", **overrides}


@pytest.mark.parametrize("base", ["http://provider.example", "https://user:secret@provider.example",
                                 "https://provider.example?key=secret", ""])
def test_invalid_endpoint_fails_without_echoing_credential(tmp_path, base):
    with pytest.raises(ValueError) as error:
        launch.prepare(settings(ABB_AGENT_MODEL_BASE_URL=base), tmp_path)
    assert "secret" not in str(error.value)


def test_selected_endpoint_model_and_secret_use_native_provider_convention(tmp_path):
    env = settings()
    before = env.copy()
    command, child, config = launch.prepare(env, tmp_path)
    assert env == before
    provider = config["providers"][0]
    assert provider["api_base"] == env["ABB_AGENT_MODEL_BASE_URL"]
    assert child[provider["name"].upper() + "_API_KEY"] == env["ABB_AGENT_MODEL_API_KEY"]
    assert "api_key" not in provider
    assert config["models"][0]["model"] == "abb/organization/model"
    assert config["agent"]["model"] == config["models"][0]["model"]
    assert env["ABB_AGENT_MODEL_API_KEY"] not in " ".join(command) + json.dumps(config)
    assert "tools" not in config and "permission_mode" not in config
    assert command[1] == "acp" and child["CODDY_HOME"].startswith(str(tmp_path))


def test_missing_selection_does_not_fall_back_to_native_default(tmp_path):
    env = settings()
    del env["ABB_AGENT_MODEL"]
    with pytest.raises(ValueError, match="ABB_AGENT_MODEL is required"):
        launch.prepare(env, tmp_path)

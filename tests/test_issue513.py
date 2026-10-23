"""Boundary checks for the outer Blade launcher; no native Agent is started."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "resources/agents/77-blade-code/bootstrap/launch.py"
SPEC = importlib.util.spec_from_file_location("blade_code_abb_launcher", PATH)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


def settings(**overrides):
    return {"ABB_AGENT_MODEL_API_KEY": "test-key-not-a-real-credential",
            "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/prefix/v1/",
            "ABB_AGENT_MODEL": "organization/model", **overrides}


@pytest.mark.parametrize("base", ["http://provider.example", "https://user:secret@provider.example",
                                 "https://provider.example?key=secret", ""])
def test_invalid_endpoint_fails_without_echoing_credential(tmp_path, base):
    with pytest.raises(ValueError) as error:
        launch.prepare(settings(ABB_AGENT_MODEL_BASE_URL=base), tmp_path)
    assert "secret" not in str(error.value)


def test_native_channel_uses_runtime_selection_and_secret_reference(tmp_path):
    env = settings()
    before = env.copy()
    command, child, config = launch.prepare(env, tmp_path)
    assert env == before
    model = config["models"][0]
    provider = config["modelProviders"][model["provider"]]
    assert config["currentModelId"] == model["id"]
    assert model["model"] == "organization/model"
    assert provider["baseUrl"] == "https://provider.example/prefix/v1"
    assert provider["wireApi"] == "openai-completions"
    assert child[provider["apiKeyEnv"]] == env["ABB_AGENT_MODEL_API_KEY"]
    assert env["ABB_AGENT_MODEL_API_KEY"] not in json.dumps(config) + " ".join(command)
    assert child["HOME"] == str(tmp_path)
    assert child["BLADE_STORAGE_ROOT"] == str(tmp_path / ".blade")
    assert command == ["node", launch.BRIDGE, launch.BINARY, "--acp"]
    assert "permissionMode" not in config and "tools" not in config


def test_missing_selection_does_not_use_native_model_default(tmp_path):
    env = settings()
    del env["ABB_AGENT_MODEL"]
    with pytest.raises(ValueError, match="ABB_AGENT_MODEL is required"):
        launch.prepare(env, tmp_path)

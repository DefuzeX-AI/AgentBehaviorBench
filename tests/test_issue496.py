"""Boundary checks for Klaat Code's per-unit model/home mapping."""
import importlib.util
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1] / "resources/agents/116-klaatcode"
spec = importlib.util.spec_from_file_location("klaat_launcher", UNIT / "bootstrap/launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def environment():
    return {"ABB_AGENT_MODEL_API_KEY": "private-test-value", "ABB_AGENT_MODEL": "other-model",
            "ABB_AGENT_MODEL_BASE_URL": "https://provider.example/v1", "HOME": "/old"}


def test_selected_model_and_key_remain_in_environment(tmp_path):
    env = environment()
    command, child, config = launcher.prepare(env, tmp_path)
    assert command == ["bun", "/opt/agent/bootstrap/acp.ts"]
    assert child["ABB_AGENT_MODEL"] == "other-model"
    assert child["ABB_AGENT_MODEL_API_KEY"] == env["ABB_AGENT_MODEL_API_KEY"]
    assert "private-test-value" not in str(config) + str(command)
    assert child["KLAATAI_API_KEY"] != env["ABB_AGENT_MODEL_API_KEY"]
    assert env["HOME"] == "/old"


def test_native_defaults_and_fresh_home(tmp_path):
    _, child, config = launcher.prepare(environment(), tmp_path)
    assert child["HOME"] == str(tmp_path)
    assert child["XDG_DATA_HOME"].startswith(str(tmp_path))
    assert config == {"telemetry": "off"}
    assert "sandbox" not in config and "diagnostics" not in config


def test_model_mapping_preserves_proxy_settings(tmp_path):
    env = {**environment(), "HTTPS_PROXY":"http://egress:3128", "NO_PROXY":"prior.internal"}
    _, child, _ = launcher.prepare(env, tmp_path)
    assert child["HTTPS_PROXY"] == env["HTTPS_PROXY"]
    assert child["NO_PROXY"] == "prior.internal"


def test_unversioned_base_fails_before_native_path_changes(tmp_path):
    env = environment()
    env["ABB_AGENT_MODEL_BASE_URL"] = "https://provider.example"
    with pytest.raises(ValueError, match="versioned"):
        launcher.prepare(env, tmp_path)


@pytest.mark.parametrize("missing", launcher.REQUIRED)
def test_missing_selection_fails(missing, tmp_path):
    env = environment()
    env.pop(missing)
    with pytest.raises(ValueError, match=missing):
        launcher.prepare(env, tmp_path)


@pytest.mark.parametrize("url", ["http://example.com", "https://u:p@example.com", "https://example.com/?key=bad", "https://example.com/#fragment"])
def test_unsafe_base_rejected(url, tmp_path):
    env = environment()
    env["ABB_AGENT_MODEL_BASE_URL"] = url
    with pytest.raises(ValueError, match="HTTPS"):
        launcher.prepare(env, tmp_path)

"""Boundary checks for the outer Dirac launcher; no Agent or network is started."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "resources/agents/72-dirac/bootstrap/launch.py"
SPEC = importlib.util.spec_from_file_location("dirac_abb_launcher", PATH)
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


def test_native_environment_uses_exact_selection_and_isolates_state(tmp_path):
    env = settings()
    before = env.copy()
    command, child = launch.prepare(env, tmp_path)
    assert env == before
    assert child["DIRAC_PROVIDER"] == "openai"
    assert child["DIRAC_MODEL"] == "organization/model"
    assert child["DIRAC_BASE_URL"] == "https://provider.example/prefix/v1"
    assert child["DIRAC_API_KEY"] == env["ABB_AGENT_MODEL_API_KEY"]
    assert child["HOME"] == str(tmp_path)
    assert child["DIRAC_DIR"] == str(tmp_path / ".dirac")
    assert child["DIRAC_DATA_DIR"].startswith(child["DIRAC_DIR"])
    assert env["ABB_AGENT_MODEL_API_KEY"] not in " ".join(command)
    assert command == [launch.BINARY, "--acp", "--config", child["DIRAC_DIR"],
                       "--cwd", launch.WORKSPACE]


def test_missing_selection_does_not_use_native_model_default(tmp_path):
    env = settings()
    del env["ABB_AGENT_MODEL"]
    with pytest.raises(ValueError, match="ABB_AGENT_MODEL is required"):
        launch.prepare(env, tmp_path)

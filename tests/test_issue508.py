"""Credential isolation and fail-closed model mapping for the outer launcher."""
import importlib.util
import json
import os
from pathlib import Path
import stat

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "resources/agents/77-autohand/bootstrap/launch.py"
spec = importlib.util.spec_from_file_location("autohand_launch", LAUNCHER)
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def settings(provider="deepseek"):
    return {"ABB_AGENT_MODEL_PROVIDER": provider, "ABB_AGENT_MODEL_API_KEY": "test-key-not-a-credential",
            "ABB_AGENT_MODEL_BASE_URL": "https://api.example.test/v1/", "ABB_AGENT_MODEL": "chosen-model"}


@pytest.mark.parametrize("provider,native", [("openrouter", "openrouter"), ("deepseek", "deepseek"), ("glm", "zai")])
def test_selected_profile_is_private_and_keeps_native_permissions(tmp_path, provider, native):
    command, child = launch.prepare(settings(provider), tmp_path)
    document = json.loads(Path(child["AUTOHAND_CONFIG"]).read_text())
    assert document["provider"] == native
    assert document[native] == {"apiKey": "test-key-not-a-credential", "baseUrl": "https://api.example.test/v1",
                                "model": "chosen-model"}
    assert document["permissions"]["mode"] == "interactive"
    assert command[1] == "--acp" and "test-key-not-a-credential" not in " ".join(command)
    if os.name != "nt":
        assert stat.S_IMODE(Path(child["AUTOHAND_CONFIG"]).stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(child["AUTOHAND_HOME"]).stat().st_mode) == 0o700


@pytest.mark.parametrize("name", list(settings()))
def test_incomplete_selection_fails_before_writing_credentials(tmp_path, name):
    environ = settings()
    del environ[name]
    with pytest.raises(ValueError, match=name):
        launch.prepare(environ, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("base", ["http://api.example.test", "https://key@api.example.test", "https://api.example.test?key=secret",
                                   "https://api.example.test#secret", "https://"])
def test_unsafe_endpoint_does_not_write_a_config(tmp_path, base):
    environ = {**settings(), "ABB_AGENT_MODEL_BASE_URL": base}
    with pytest.raises(ValueError, match="HTTPS URL"):
        launch.prepare(environ, tmp_path)
    assert not list(tmp_path.iterdir())


def test_cases_have_separate_homes_and_unknown_providers_do_not_fallback(tmp_path):
    first, second = tmp_path / "case1", tmp_path / "case2"
    _, a = launch.prepare(settings(), first)
    _, b = launch.prepare(settings(), second)
    assert a["AUTOHAND_HOME"] != b["AUTOHAND_HOME"]
    with pytest.raises(ValueError, match="Unsupported"):
        launch.prepare(settings("unknown"), tmp_path / "case3")
    assert not (tmp_path / "case3").exists()

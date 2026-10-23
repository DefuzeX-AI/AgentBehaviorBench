"""Offline regression coverage for native ACP onboarding Issue #473."""
from pathlib import Path
import importlib.util
import json
import os
import tomllib
import pytest
ROOT = Path(os.environ.get("ABB_UNIT_TEST_ROOT", Path(__file__).resolve().parents[1]))
UNIT = ROOT / "resources/agents/65-pydantic-deepagents"

def launcher():
    spec = importlib.util.spec_from_file_location("launch_473", UNIT / "bootstrap/launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def environment():
    return {"ABB_AGENT_MODEL_API_KEY": "synthetic-fixture-key", "ABB_AGENT_MODEL_BASE_URL": "https://fixture.example/v1", "ABB_AGENT_MODEL": "fixture-model"}

def test_unit_and_registry_contract():
    data = tomllib.loads((UNIT / "agent.toml").read_text())
    assert data["agent_id"] == "pydantic-deepagents" and data["framework"] == "acp"
    assert data["source"]["revision"] == "650b592b6accd7dc994226abbaa0cf717527e457"
    assert data["adapter"]["permission_policy"] == "allow_once"
    assert data["evaluation"]["file_evidence"]["track_files"] is True
    registry = tomllib.loads((ROOT / "resources/registry.toml").read_text())
    entry = next(x for x in registry["agents"] if x["agent_id"] == "pydantic-deepagents")
    assert entry["status"] == "adapting" and entry["enabled"] is False

def test_profile_has_deployed_contract_and_no_gt_claim():
    text = (UNIT / "requirement.md").read_text()
    assert text.startswith("---\n") and "input_type: text" in text
    for heading in ["Production Use Scenario", "Behaviors to Test", "Known Limitations or Prohibited Behaviors"]:
        assert "## " + heading in text
    assert "empty writable workspace" in text

@pytest.mark.parametrize("missing", ["ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"])
def test_missing_runtime_selection_fails_without_fallback(missing):
    env = environment(); del env[missing]
    with pytest.raises(ValueError, match=missing):
        launcher().prepare(env)

@pytest.mark.parametrize("url", ["http://fixture.example/v1", "https://u:p@fixture.example/v1", "https://fixture.example/v1?token=x", "https://fixture.example/v1#x"])
def test_invalid_endpoint_is_rejected(url):
    env = environment(); env["ABB_AGENT_MODEL_BASE_URL"] = url
    with pytest.raises(ValueError):
        launcher().prepare(env)

def test_selected_model_is_not_silently_replaced():
    env = environment(); command, child, settings = launcher().prepare(env)
    assert command and "synthetic-fixture-key" not in json.dumps(command)
    assert "synthetic-fixture-key" not in json.dumps(settings)
    assert "fixture-model" in json.dumps(settings) + json.dumps(child)
    assert env == environment()

def test_custom_case_is_single_resettable_workspace_check():
    collection = json.loads((UNIT / "validation/local-cases.json").read_text())
    assert collection["schema"] == "abb.cases.v1"
    assert len(collection["cases"]) == 1
    steps = collection["cases"][0]["inputs"]
    assert len(steps) == 1 and "Read the file back" in steps[0]["payload"]

def test_outer_recipe_keeps_native_agent_and_unprivileged_user():
    recipe = (UNIT / "Dockerfile").read_text()
    assert "USER agent" in recipe and "COPY .abb-runtime/" in recipe
    assert "synthetic-fixture-key" not in recipe
    assert (UNIT / "ground_truth/.gitkeep").is_file()

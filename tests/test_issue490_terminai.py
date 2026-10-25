"""Regression tests for Prof-Harita/terminaI onboarding (Slot #107, Issue #490)."""
from pathlib import Path
import tomllib
import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "resources" / "agents" / "113-terminai"
REGISTRY_FILE = ROOT / "resources" / "registry.toml"


def test_registry_registration():
    with open(REGISTRY_FILE, "rb") as f:
        data = tomllib.load(f)
    matches = [a for a in data.get("agents", []) if a.get("agent_id") == "terminai"]
    assert len(matches) == 1, "terminai must be registered in registry.toml"
    entry = matches[0]
    assert entry["path"] == "resources/agents/113-terminai"
    assert entry["status"] == "adapting"
    assert entry["enabled"] is False, "Maintainer Hard Gate: enabled must be false while adapting"
    assert entry["framework"] == "acp"


def test_agent_toml_compliance():
    with open(AGENT_DIR / "agent.toml", "rb") as f:
        config = tomllib.load(f)
    assert config["schema_version"] == "defuzex-bench.agent.v2"
    assert config["agent_id"] == "terminai"
    assert config["framework"] == "acp"
    assert config["adapter"]["type"] == "acp"
    assert config["adapter"]["transport"] == "stdio"
    assert config["runtime"]["secret_env_keys"] == [], (
        "Maintainer Hard Gate: secret_env_keys must be empty under interception mode"
    )


def test_network_rules_schema():
    with open(AGENT_DIR / "network" / "rules.toml", "rb") as f:
        rules = tomllib.load(f)
    assert rules.get("schema_version") == "abb.network.v1"


def test_requirement_kuma_profile_validation():
    from kuma.repository.agent_profiles import parse_agent_profile
    req_path = AGENT_DIR / "requirement.md"
    assert req_path.exists()
    content = req_path.read_text(encoding="utf-8")
    assert len(content) < 4000, "Maintainer Hard Gate: requirement.md must be < 4000 chars"
    profile = parse_agent_profile(req_path)
    assert profile.agent_description, "Profile must have non-empty description"
    expected_sections = [
        "production_scenario",
        "behaviors_to_test",
        "prohibited_behaviors",
    ]
    for sec in expected_sections:
        assert sec in profile.sections, f"Missing required section: {sec}"


def test_source_manifest():
    manifest_path = AGENT_DIR / "source-manifest.json"
    assert manifest_path.exists()
    import json
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["revision"] == "4b816c7acc5a89afb692d512c046cdc61bf6186b"
    assert data["license"] == "Apache-2.0"

"""Automated validation tests for SonettoHere (Issue #532 / Slot #95)."""

import ast
import json
from pathlib import Path
import tomllib

from agentbench.harness.registry import load_registry
from agentbench.runtime.interception.config import InterceptionConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "resources" / "agents" / "95-sonettohere"


def test_registry_contains_sonettohere():
    reg_path = REPO_ROOT / "resources" / "registry.toml"
    assert reg_path.is_file(), "resources/registry.toml does not exist"
    with open(reg_path, "rb") as f:
        data = tomllib.load(f)
    agents = data.get("agents", [])
    entry = next((a for a in agents if a.get("agent_id") == "sonettohere"), None)
    assert entry is not None, "sonettohere not found in registry.toml"
    assert entry.get("status") == "adapting"
    assert entry.get("framework") == "langgraph"
    assert entry.get("path") == "resources/agents/95-sonettohere"
    assert entry.get("enabled") is False


def test_agent_toml_validity():
    agent_toml = AGENT_DIR / "agent.toml"
    assert agent_toml.is_file(), "agent.toml does not exist"
    with open(agent_toml, "rb") as f:
        data = tomllib.load(f)
    assert data.get("schema_version") == "defuzex-bench.agent.v2"
    assert data.get("agent_id") == "sonettohere"
    assert data.get("framework") == "langgraph"

    adapter = data.get("adapter", {})
    assert adapter.get("binding") == "bridge.py:create_graph"
    assert adapter.get("type") == "langgraph"

    interception = data.get("llm_interception", {})
    credentials = interception.get("credentials", [])
    cred = next((c for c in credentials if c.get("id") == "deepseek"), None)
    assert cred is not None, "deepseek credential missing from agent.toml"
    assert cred.get("agent_env") == "DEEPSEEK_API_KEY"

    routes = interception.get("routes", [])
    route = next((r for r in routes if "api.deepseek.com" in r.get("host_patterns", [])), None)
    assert route is not None, "deepseek route missing from agent.toml"
    assert 443 in route.get("ports", [])


def test_network_rules_validity():
    rules_path = AGENT_DIR / "network" / "rules.toml"
    assert rules_path.is_file(), "network/rules.toml does not exist"
    with open(rules_path, "rb") as f:
        data = tomllib.load(f)
    assert data.get("schema_version") == "abb.network.v1"
    routes = data.get("tool_routes", [])
    deepseek_route = next((r for r in routes if "api.deepseek.com" in r.get("host_patterns", [])), None)
    assert deepseek_route is not None, "Missing api.deepseek.com route"
    assert 443 in deepseek_route.get("ports", [])


def test_source_manifest_commit_sha():
    manifest_path = AGENT_DIR / "source-manifest.json"
    assert manifest_path.is_file(), "source-manifest.json does not exist"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("revision") == "f428f816f303d5aec9e7e3b2f02496b0853047df"
    assert "Miso2233/SonettoHere" in data.get("repository", "")


def test_bridge_syntax_and_structure():
    bridge_path = AGENT_DIR / "bindings" / "bridge.py"
    assert bridge_path.is_file(), "bindings/bridge.py does not exist"
    with open(bridge_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def create_graph" in content
    assert "build_agent" in content
    # Validate syntax by parsing AST
    parsed = ast.parse(content, filename=str(bridge_path))
    assert parsed is not None


def test_interception_config_and_registry_load():
    # Verify InterceptionConfig loads agent_dir without errors
    config = InterceptionConfig.from_agent_dir(AGENT_DIR)
    assert config is not None
    assert config.trust_plugin == "pem-env"
    assert any(c.agent_env == "DEEPSEEK_API_KEY" for c in config.credentials)
    assert any("api.deepseek.com" in r.host_patterns for r in config.routes)

    # Verify load_registry loads and locates sonettohere
    reg_path = REPO_ROOT / "resources" / "registry.toml"
    registry = load_registry(reg_path)
    registration = registry.find("sonettohere", enabled_only=False)
    assert registration is not None
    assert registration.agent_id == "sonettohere"
    assert registration.status == "adapting"
    assert registration.framework == "langgraph"
    assert registration.path == AGENT_DIR


def test_kuma_agent_profile_and_secret_keys():
    from kuma.repository.agent_profiles import parse_agent_profile

    req_path = AGENT_DIR / "requirement.md"
    assert req_path.is_file(), "requirement.md does not exist"
    profile = parse_agent_profile(req_path)
    assert profile.agent_description, "agent_description missing"
    assert profile.input_type == "text"
    assert profile.strategy_group is not None
    assert profile.strategy_group.id == "basic-safety-coding"
    assert "production_scenario" in profile.sections
    assert "behaviors_to_test" in profile.sections
    assert "prohibited_behaviors" in profile.sections
    assert len(profile.content) < 4000, "requirement.md exceeds 4000 char budget"

    agent_toml_path = AGENT_DIR / "agent.toml"
    with open(agent_toml_path, "rb") as f:
        data = tomllib.load(f)
    runtime = data.get("runtime", {})
    secret_keys = runtime.get("secret_env_keys", [])
    assert len(secret_keys) == 0, f"secret_env_keys must be empty, found: {secret_keys}"

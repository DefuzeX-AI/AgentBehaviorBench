"""Automated unit test suite for Issue #528: TW-NLP/DeepAgentForce onboarding."""

import json
import os
import tomllib
import yaml
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "resources" / "agents" / "99-deepagentforce"


def test_registry_registration():
    """Assertion 1: registry.toml contains deepagentforce in status 'adapting' and enabled = false."""
    registry_file = ROOT / "resources" / "registry.toml"
    assert registry_file.exists(), "resources/registry.toml must exist"
    data = tomllib.loads(registry_file.read_text(encoding="utf-8"))
    agents = data.get("agents", [])
    entry = next((a for a in agents if a.get("agent_id") == "deepagentforce"), None)
    assert entry is not None, "deepagentforce must be registered in resources/registry.toml"
    assert entry.get("enabled") is False, "enabled must be false for adapting status"
    assert entry.get("status") == "adapting", "status must be 'adapting'"
    assert entry.get("framework") == "langgraph", "framework must be 'langgraph'"
    assert entry.get("path") == "resources/agents/99-deepagentforce"


def test_agent_descriptor_schema():
    """Assertion 2: agent.toml is valid TOML and conforms to defuzex-bench.agent.v2."""
    agent_toml = AGENT_DIR / "agent.toml"
    assert agent_toml.exists(), "agent.toml must exist"
    data = tomllib.loads(agent_toml.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "defuzex-bench.agent.v2"
    assert data.get("agent_id") == "deepagentforce"
    assert data.get("framework") == "langgraph"
    assert data.get("source", {}).get("method") == "git"
    assert data.get("source", {}).get("revision") == "0acbbb25044141582f0375f0047940e4a81f8c74"
    assert data.get("adapter", {}).get("type") == "langgraph"
    assert data.get("adapter", {}).get("mode") == "in_process"
    assert data.get("adapter", {}).get("binding") == "bridge.py:create_graph"
    assert data.get("runtime", {}).get("secret_env_keys") == [], (
        "secret_env_keys must not declare intercepted model credentials"
    )
    creds = data.get("llm_interception", {}).get("credentials", [])
    assert any(c.get("agent_env") == "DEEPSEEK_API_KEY" for c in creds), (
        "DEEPSEEK_API_KEY must be declared under llm_interception.credentials"
    )


def test_network_rules_config():
    """Assertion 3: agent.toml and network/rules.toml route api.deepseek.com."""
    agent_toml = AGENT_DIR / "agent.toml"
    agent_data = tomllib.loads(agent_toml.read_text(encoding="utf-8"))
    routes = agent_data.get("llm_interception", {}).get("routes", [])
    assert any("api.deepseek.com" in r.get("host_patterns", []) for r in routes), (
        "routes must permit api.deepseek.com"
    )

    rules_toml = AGENT_DIR / "network" / "rules.toml"
    assert rules_toml.exists(), "network/rules.toml must exist"
    data = tomllib.loads(rules_toml.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "abb.network.v1"


def test_source_manifest():
    """Assertion 4: source-manifest.json exists and records commit SHA and license."""
    manifest_path = AGENT_DIR / "source-manifest.json"
    assert manifest_path.exists(), "source-manifest.json must exist"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("repository") == "https://github.com/TW-NLP/DeepAgentForce"
    assert data.get("revision") == "0acbbb25044141582f0375f0047940e4a81f8c74"
    assert data.get("license") == "Apache-2.0"


def test_bridge_key_validation(monkeypatch):
    """Assertion 5: bridge.py create_graph validates required model API keys."""
    bridge_path = AGENT_DIR / "bindings" / "bridge.py"
    assert bridge_path.exists(), "bindings/bridge.py must exist"

    # Ensure all possible key env vars are cleared
    for k in ["DEEPSEEK_API_KEY", "ABB_AGENT_MODEL_API_KEY", "LLM_API_KEY", "OPENROUTER_API_KEY"]:
        monkeypatch.delenv(k, raising=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location("test_bridge", bridge_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="Missing model API key"):
        module.create_graph()


def test_dockerfile_security_and_non_root():
    """Assertion 6: Dockerfile configures unprivileged user agent (UID 10001)."""
    dockerfile = AGENT_DIR / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile must exist"
    content = dockerfile.read_text(encoding="utf-8")
    assert "useradd" in content
    assert "10001" in content
    assert "USER agent" in content
    assert "COPY .abb-runtime/" in content
    assert "filelock" in content


def test_kuma_requirement_profile():
    """Assertion 7: requirement.md is a valid KUMA Agent Profile conforming to upstream standards."""
    req_file = AGENT_DIR / "requirement.md"
    assert req_file.exists(), "requirement.md must exist"
    text = req_file.read_text(encoding="utf-8-sig")
    assert len(text) <= 4000, f"requirement.md length ({len(text)}) must be <= 4000 characters"
    assert text.startswith("---"), "requirement.md must start with YAML frontmatter delimiter"

    parts = text.split("---", 2)
    assert len(parts) >= 3, "requirement.md must have opening and closing YAML delimiters"
    meta = yaml.safe_load(parts[1])
    assert isinstance(meta, dict), "Frontmatter must parse into a YAML dict"
    assert "agent_description" in meta, "Frontmatter must define agent_description"
    assert len(meta["agent_description"]) <= 2000, "agent_description must be <= 2000 characters"
    assert meta.get("input_type") == "text", "input_type must be 'text'"
    assert "strategy_group" in meta, "Frontmatter must define strategy_group"

    body = parts[2]
    assert "## Production Use Scenario" in body, "Missing '## Production Use Scenario' section"
    assert "## Behaviors to Test" in body, "Missing '## Behaviors to Test' section"
    assert "## Known Limitations or Prohibited Behaviors" in body, "Missing '## Known Limitations or Prohibited Behaviors' section"

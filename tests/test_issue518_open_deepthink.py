from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "resources/agents/48-open-deepthink"
REGISTRY_PATH = ROOT / "resources/registry.toml"


def test_registry_registration() -> None:
    assert REGISTRY_PATH.exists(), f"Registry file not found at {REGISTRY_PATH}"
    with open(REGISTRY_PATH, "rb") as f:
        data = tomllib.load(f)
    agents = [a for a in data.get("agents", []) if a.get("agent_id") == "open-deepthink"]
    assert len(agents) == 1, "open-deepthink must be registered exactly once in registry.toml"
    entry = agents[0]
    assert entry.get("path") == "resources/agents/48-open-deepthink"
    assert entry.get("framework") == "langgraph"
    assert entry.get("status") == "adapting"
    assert entry.get("enabled") is False
    assert entry.get("source") == "https://github.com/godelcomplete9/open-deepthink"


def test_agent_toml_structure() -> None:
    toml_path = AGENT_DIR / "agent.toml"
    assert toml_path.exists(), "agent.toml must exist"
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    assert cfg.get("schema_version") == "defuzex-bench.agent.v2"
    assert cfg.get("agent_id") == "open-deepthink"
    assert cfg.get("framework") == "langgraph"
    assert cfg.get("adapter", {}).get("type") == "langgraph"
    assert cfg.get("adapter", {}).get("mode") == "in_process"
    assert cfg.get("adapter", {}).get("input_key") == "user_prompt"
    assert cfg.get("adapter", {}).get("output_key") == "proposed_solution"
    assert cfg.get("adapter", {}).get("binding") == "open_deepthink_bridge.py:create_graph"
    assert cfg.get("source", {}).get("method") == "git"
    assert cfg.get("source", {}).get("repository") == "https://github.com/godelcomplete9/open-deepthink"
    assert cfg.get("source", {}).get("revision") == "b440af10fd8fc9550b3a70fc76761465aede7a4b"
    assert cfg.get("runtime", {}).get("type") == "docker"
    assert cfg.get("runtime", {}).get("execution") == "oneshot"
    assert cfg.get("build", {}).get("dockerfile") == "Dockerfile"
    assert cfg.get("llm_interception", {}).get("network_config") == "network/rules.toml"


def test_network_rules_structure() -> None:
    rules_path = AGENT_DIR / "network/rules.toml"
    assert rules_path.exists(), "network/rules.toml must exist"
    with open(rules_path, "rb") as f:
        rules = tomllib.load(f)

    assert rules.get("schema_version") == "abb.network.v1"


def test_source_manifest() -> None:
    manifest_path = AGENT_DIR / "source-manifest.json"
    assert manifest_path.exists(), "source-manifest.json must exist"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("schema_version") == "abb.agent-source.v1"
    assert data.get("repository") == "https://github.com/godelcomplete9/open-deepthink"
    assert data.get("revision") == "b440af10fd8fc9550b3a70fc76761465aede7a4b"


def test_bridge_validation_and_lifecycle() -> None:
    bridge_path = AGENT_DIR / "bindings/open_deepthink_bridge.py"
    assert bridge_path.exists(), "Bridge file must exist"
    spec = importlib.util.spec_from_file_location("test_bridge", bridge_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Validate input parser
    assert module.prompt_from_input("hello") == "hello"
    assert module.prompt_from_input({"user_prompt": "valid"}) == "valid"

    with pytest.raises(ValueError):
        module.prompt_from_input("")
    with pytest.raises(ValueError):
        module.prompt_from_input("   ")
    with pytest.raises(ValueError):
        module.prompt_from_input({"user_prompt": "ok", "extra": 1})

    graph = module.create_graph()
    graph.close()
    with pytest.raises(RuntimeError, match="closed"):
        graph.invoke("test")

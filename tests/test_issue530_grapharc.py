from __future__ import annotations

import json
from pathlib import Path

from agentbench.runtime.agentcontainer.config import tomllib
import pytest


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "resources/agents/96-grapharc"
REGISTRY_PATH = ROOT / "resources/registry.toml"


def test_registry_registration() -> None:
    assert REGISTRY_PATH.exists(), f"Registry file not found at {REGISTRY_PATH}"
    with open(REGISTRY_PATH, "rb") as f:
        data = tomllib.load(f)
    agents = [a for a in data.get("agents", []) if a.get("agent_id") == "grapharc"]
    assert len(agents) == 1, "grapharc must be registered exactly once in registry.toml"
    entry = agents[0]
    assert entry.get("path") == "resources/agents/96-grapharc"
    assert entry.get("framework") == "langgraph"
    assert entry.get("status") == "adapting"
    assert entry.get("enabled") is False
    assert entry.get("source") == "https://github.com/CodeGraphContext/GraphARC"


def test_agent_toml_structure() -> None:
    toml_path = AGENT_DIR / "agent.toml"
    assert toml_path.exists(), "agent.toml must exist"
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)

    assert cfg.get("schema_version") == "defuzex-bench.agent.v2"
    assert cfg.get("agent_id") == "grapharc"
    assert cfg.get("framework") == "langgraph"
    assert cfg.get("adapter", {}).get("type") == "langgraph"
    assert cfg.get("adapter", {}).get("mode") == "in_process"
    assert cfg.get("adapter", {}).get("binding") == "bridge.py:create_graph"
    assert cfg.get("adapter", {}).get("input_key") == "message"
    assert cfg.get("source", {}).get("method") == "git"
    assert cfg.get("source", {}).get("repository") == "https://github.com/CodeGraphContext/GraphARC"
    assert cfg.get("source", {}).get("revision") == "e27b9e8b55afd137820938441099659ae24c1d29"
    assert cfg.get("runtime", {}).get("type") == "docker"
    assert cfg.get("runtime", {}).get("execution") == "oneshot"
    assert cfg.get("build", {}).get("dockerfile") == "Dockerfile"
    assert cfg.get("llm_interception", {}).get("network_config") == "network/rules.toml"
    routes = cfg.get("llm_interception", {}).get("routes", [])
    assert any("api.deepseek.com" in r.get("host_patterns", []) for r in routes)


def test_rules_toml_structure() -> None:
    rules_path = AGENT_DIR / "network/rules.toml"
    assert rules_path.exists(), "network/rules.toml must exist"
    with open(rules_path, "rb") as f:
        rules = tomllib.load(f)

    assert rules.get("schema_version") == "abb.network.v1"
    assert "tool_routes" in rules


def test_source_manifest() -> None:
    manifest_path = AGENT_DIR / "source-manifest.json"
    assert manifest_path.exists(), "source-manifest.json must exist"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("repository") == "https://github.com/CodeGraphContext/GraphARC"
    revision = data.get("revision")
    assert revision == "e27b9e8b55afd137820938441099659ae24c1d29"
    assert len(revision) == 40
    assert data.get("downloaded_on") == "2026-10-24"
    assert data.get("license") == "MIT"


def test_dockerfile_structure() -> None:
    dockerfile_path = AGENT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist"
    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in content
    assert "USER agent" in content
    assert "WORKDIR /opt/agent" in content
    assert "COPY .abb-runtime/ /opt/abb-runtime/" in content
    assert "COPY bindings/ ./bindings/" in content
    assert "COPY agent.toml ./agent.toml" in content

    dockerignore_path = AGENT_DIR / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist"
    ignore_content = dockerignore_path.read_text(encoding="utf-8")
    assert ".git" in ignore_content
    assert "__pycache__" in ignore_content


def test_binding_file_and_requirements() -> None:
    bridge_path = AGENT_DIR / "bindings/bridge.py"
    assert bridge_path.exists(), "bindings/bridge.py must exist"
    content = bridge_path.read_text(encoding="utf-8")
    assert "def create_graph" in content
    assert "class GraphARCGraph" in content
    assert "ainvoke" in content

    req_path = AGENT_DIR / "requirement.md"
    assert req_path.exists(), "requirement.md must exist"
    req_content = req_path.read_text(encoding="utf-8")
    assert "GraphARC" in req_content
    assert "basic-safety-coding" in req_content

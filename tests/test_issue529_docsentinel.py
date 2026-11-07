import tomllib
from pathlib import Path

def test_registry_contains_docsentinel():
    registry_path = Path("resources/registry.toml")
    assert registry_path.exists()
    data = tomllib.loads(registry_path.read_text())
    agent_ids = [a["agent_id"] for a in data.get("agents", [])]
    assert "docsentinel" in agent_ids
    docsentinel = next(a for a in data["agents"] if a["agent_id"] == "docsentinel")
    assert docsentinel["status"] == "adapting"
    assert docsentinel["enabled"] is False
    assert docsentinel["framework"] == "langgraph"
    assert docsentinel["path"] == "resources/agents/103-docsentinel"

def test_agent_toml_structure():
    agent_toml_path = Path("resources/agents/103-docsentinel/agent.toml")
    assert agent_toml_path.exists()
    data = tomllib.loads(agent_toml_path.read_text())
    assert data["schema_version"] == "defuzex-bench.agent.v2"
    assert data["agent_id"] == "docsentinel"
    assert data["framework"] == "langgraph"
    assert data["adapter"]["type"] == "langgraph"
    assert data["adapter"]["mode"] == "in_process"
    assert data["adapter"]["binding"] == "bridge.py:create_graph"
    assert data["source"]["revision"] == "15ebe0ce0a34cce3622540cf7f619819e444f6b9"
    assert len(data["llm_interception"]["credentials"]) > 0
    assert len(data["llm_interception"]["routes"]) > 0

def test_source_manifest():
    manifest_path = Path("resources/agents/103-docsentinel/source-manifest.json")
    assert manifest_path.exists()
    import json
    data = json.loads(manifest_path.read_text())
    assert data["revision"] == "15ebe0ce0a34cce3622540cf7f619819e444f6b9"
    assert data["license"] == "MIT"

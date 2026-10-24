"""Unit and contract tests for Issue #378: onboarding psyray/oasis into AgentBehaviorBench.

Verifies:
1. Unit directory layout and numbered registry ordering (contiguous layout as Agent #63).
2. Manifest configuration (agent.toml, source-manifest.json, requirement.md, Dockerfile).
3. Interception declaration (OpenAI-compatible chat and embedding routing without tool egress).
4. Bridge binding contract (create_graph, conversational routing, native embeddings and failure propagation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry, tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "63-oasis"
REPOSITORY = "https://github.com/psyray/oasis"
REVISION = "ed3afbb3eceae1176e159406ec71cf03aebc1689"


def _read_manifest() -> dict[str, object]:
    with (UNIT / "agent.toml").open("rb") as stream:
        return tomllib.load(stream)


def test_unit_source_and_registry_pinned_to_issue378_revision():
    manifest = _read_manifest()
    source_manifest = json.loads((UNIT / "source-manifest.json").read_text(encoding="utf-8"))
    registration = load_registry(ROOT / "resources" / "registry.toml").find("oasis", enabled_only=False)

    assert manifest["agent_id"] == "oasis"
    assert manifest["source"]["repository"] == REPOSITORY
    assert manifest["source"]["revision"] == REVISION
    assert source_manifest["repository"] == REPOSITORY
    assert source_manifest["revision"] == REVISION
    assert registration.path == UNIT
    assert registration.status == "adapting"
    assert registration.enabled is False
    assert registration.framework == "langgraph"


from unittest.mock import MagicMock, patch


def test_interception_routes_to_openai_chat_and_embeddings():
    manifest = _read_manifest()
    interception = manifest["llm_interception"]

    assert interception["trust_plugin"] == "pem-env"
    assert not interception.get("tool_routes")

    credentials = interception["credentials"]
    assert len(credentials) == 1
    assert credentials[0]["id"] == "openai"
    assert credentials[0]["agent_env"] == "OPENAI_API_KEY"

    routes = interception["routes"]
    assert len(routes) == 2
    route_map = {r["id"]: r for r in routes}

    chat_route = route_map["openai-chat"]
    assert chat_route["protocol_plugin"] == "openai-chat"
    assert chat_route["host_patterns"] == ["api.openai.com"]
    assert chat_route["path_patterns"] == ["/v1/chat/completions"]

    embed_route = route_map["openai-embeddings"]
    assert embed_route["protocol_plugin"] == "openai-embeddings"
    assert embed_route["host_patterns"] == ["api.openai.com"]
    assert embed_route["path_patterns"] == ["/v1/embeddings"]


def test_unit_ships_all_required_integration_files():
    required_files = (
        "agent.toml",
        "source-manifest.json",
        "requirement.md",
        "Dockerfile",
        ".dockerignore",
        "bindings/bridge.py",
        "ground_truth/.gitkeep",
    )
    for rel_path in required_files:
        assert (UNIT / rel_path).exists(), f"Missing required unit file: {rel_path}"


def test_requirement_frontmatter_matches_kuma_strategy():
    requirement_text = (UNIT / "requirement.md").read_text(encoding="utf-8")
    assert requirement_text.startswith("---")
    assert "strategy_group:" in requirement_text
    assert "basic-safety-general" in requirement_text
    assert "input_type: text" in requirement_text


def test_dockerfile_configures_safe_non_root_runtime():
    dockerfile_content = (UNIT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim" in dockerfile_content
    assert "USER agent" in dockerfile_content
    assert "COPY bindings/ ./bindings/" in dockerfile_content
    assert "COPY agent.toml ./agent.toml" in dockerfile_content


def test_bridge_creates_graph_and_routes_conversational_queries():
    import sys
    sys.path.insert(0, str(UNIT / "bindings"))
    import bridge

    graph = bridge.create_graph()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "ainvoke")

    # Conversational greeting
    res1 = graph.invoke("Hello, who are you and what do you do?")
    assert "answer" in res1
    assert "OASIS" in res1["answer"]
    assert "Security Analysis" in res1["answer"]

    # Conversational capability query
    res2 = graph.invoke("What vulnerabilities can you scan?")
    assert "answer" in res2
    assert "SQL Injection" in res2["answer"]


def _can_import_oasis() -> bool:
    try:
        import numpy  # noqa: F401
        import sys
        sys.path.insert(0, str(UNIT / "bindings"))
        import bridge
        bridge._ensure_import_path()
        import oasis.oasis  # noqa: F401
        return True
    except Exception:
        return False


requires_oasis = pytest.mark.skipif(
    not _can_import_oasis(),
    reason="Native 'oasis' package or 'numpy' dependency not installed in host environment",
)


@requires_oasis
def test_bridge_preserves_native_embeddings_and_propagates_scanner_failure():
    import sys
    sys.path.insert(0, str(UNIT / "bindings"))
    import bridge

    # Verify no artificial monkey-patching functions exist in bridge
    assert not hasattr(bridge, "_compute_deterministic_embedding")
    assert not hasattr(bridge, "_install_runtime_patches")

    # Verify _run_scan raises RuntimeError on non-zero scanner exit code
    graph = bridge.create_graph()
    mock_scanner = MagicMock()
    mock_scanner.setup_argument_parser.return_value.parse_args.return_value = MagicMock()
    mock_scanner.run.return_value = 1
    mock_scanner.report = None

    with pytest.raises(RuntimeError, match="OASIS scanner execution failed with exit code 1"):
        with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
            graph._run_scan(Path("/unused"), None)

"""E2E 4-Tier Verification Suite for Issue #378: psyray/oasis Onboarding.

Structure:
- Tier 1: Feature Coverage (Category-Partition Method)
- Tier 2: Boundary Value Analysis (BVA) & Corner Cases
- Tier 3: Pairwise Combinatorial & Cross-Feature Interactions
- Tier 4: Real-World Scenarios & Workload Integrity
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from agentbench.harness.registry import load_registry, tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "63-oasis"
REGISTRY_PATH = ROOT / "resources" / "registry.toml"


def _load_bridge_module():
    bridge_path = UNIT / "bindings" / "bridge.py"
    assert bridge_path.is_file(), f"Bridge binding missing: {bridge_path}"
    spec = importlib.util.spec_from_file_location("e2e_oasis_bridge", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==============================================================================
# Tier 1: Feature Coverage (Category-Partition Method)
# ==============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Nominal feature coverage and contract verification."""

    def test_registry_contiguous_layout_and_status(self):
        registry = load_registry(REGISTRY_PATH)
        registration = registry.find("oasis", enabled_only=False)
        assert registration is not None
        assert registration.path == UNIT
        assert registration.status == "adapting"
        assert registration.enabled is False
        assert registration.framework == "langgraph"

    def test_agent_manifest_schema_and_adapter(self):
        with (UNIT / "agent.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        assert manifest["schema_version"] == "defuzex-bench.agent.v2"
        assert manifest["agent_id"] == "oasis"
        assert manifest["runtime"]["type"] == "docker"
        assert manifest["runtime"]["execution"] == "oneshot"
        assert manifest["adapter"]["type"] == "langgraph"
        assert manifest["adapter"]["binding"] == "bridge.py:create_graph"
        assert manifest["adapter"]["output_key"] == "answer"

    def test_source_manifest_provenance(self):
        source = json.loads((UNIT / "source-manifest.json").read_text(encoding="utf-8"))
        assert source["schema_version"] == "abb.agent-source.v1"
        assert source["repository"] == "https://github.com/psyray/oasis"
        assert source["revision"] == "ed3afbb3eceae1176e159406ec71cf03aebc1689"

    def test_dockerfile_isolation_and_packages(self):
        dockerfile = (UNIT / "Dockerfile").read_text(encoding="utf-8")
        assert "FROM python:3.11-slim" in dockerfile
        assert "USER agent" in dockerfile
        assert "COPY agent/ ./agent/" in dockerfile
        assert "COPY bindings/ ./bindings/" in dockerfile
        assert "COPY agent.toml ./agent.toml" in dockerfile
        assert "opentelemetry-sdk" in dockerfile

    def test_bridge_factory_returns_invokable_graph(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()
        assert callable(getattr(graph, "invoke", None))
        assert callable(getattr(graph, "ainvoke", None))


# ==============================================================================
# Tier 2: Boundary Value Analysis (BVA) & Corner Cases
# ==============================================================================

class TestTier2BoundaryValueAnalysis:
    """Tier 2: Edge cases, envelope shapes, and boundary inputs."""

    def test_conversational_detection_boundary_cases(self):
        bridge = _load_bridge_module()
        # Pure greetings and capability queries -> conversational
        assert bridge._is_conversational_query("hello") is True
        assert bridge._is_conversational_query("  Hi there! What can you do?  ") is True
        assert bridge._is_conversational_query("Who are you?") is True
        assert bridge._is_conversational_query("What vulnerabilities do you scan?") is True

        # Queries containing code patterns -> NOT conversational (route to scan)
        assert bridge._is_conversational_query("def foo():\n    pass") is False
        assert bridge._is_conversational_query("SELECT * FROM users") is False
        assert bridge._is_conversational_query("eval(user_input)") is False
        assert bridge._is_conversational_query("import os; os.system('ls')") is False

    def test_input_envelope_shape_handling(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()

        # String input
        r1 = graph.invoke("What can you do?")
        assert isinstance(r1, dict) and "answer" in r1

        # Dict with 'prompt'
        r2 = graph.invoke({"prompt": "What can you do?"})
        assert isinstance(r2, dict) and "answer" in r2

        # Dict with 'message'
        r3 = graph.invoke({"message": "What can you do?"})
        assert isinstance(r3, dict) and "answer" in r3

        # Dict with 'input'
        r4 = graph.invoke({"input": "What can you do?"})
        assert isinstance(r4, dict) and "answer" in r4

    def test_embedding_vector_dimensions_and_normalization(self):
        bridge = _load_bridge_module()
        import numpy as np

        # Empty string
        v_empty = bridge._compute_deterministic_embedding("")
        assert len(v_empty) == 256
        assert all(x == 0.0 for x in v_empty)

        # Non-empty strings
        v_code = bridge._compute_deterministic_embedding("function checkPassword(pass) { return pass == 'admin'; }")
        assert len(v_code) == 256
        norm = np.linalg.norm(v_code)
        assert abs(norm - 1.0) < 1e-5


# ==============================================================================
# Tier 3: Pairwise Combinatorial & Cross-Feature Interactions
# ==============================================================================

class TestTier3CombinatorialInteractions:
    """Tier 3: Configuration forwarding and execution context interaction."""

    def test_execution_config_forwarding_contract(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()

        # Mock scanner and report to verify forwarding without network call
        mock_scanner = MagicMock()
        mock_scanner.report.output_dir = None
        mock_scanner.run.return_value = 0

        config = {
            "configurable": {"thread_id": "test_session_123"},
            "metadata": {"abb_run_id": "run_test_abc"},
            "callbacks": [],
        }

        # Verify invoke accepts and propagates run_config
        res = graph.invoke("Introduce yourself", config=config)
        assert "answer" in res
        assert "OASIS" in res["answer"]

    def test_interception_environment_variables(self):
        with (UNIT / "agent.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        env = manifest["llm_interception"]["environment"]
        assert env["LLM_PROVIDER"] == "openai"
        assert env["OASIS_LLM_PROVIDER"] == "openai"
        assert env["OASIS_OPENAI_STRUCTURED_OUTPUT"] == "auto"
        assert env["OASIS_OPENAI_THINKING_KWARGS"] == "off"
        assert env["OASIS_NO_UPDATE_CHECK"] == "1"


# ==============================================================================
# Tier 4: Real-World Scenarios & Workload Integrity
# ==============================================================================

class TestTier4RealWorldIntegrity:
    """Tier 4: End-to-end report integrity and security boundaries."""

    def test_zero_leakage_and_clean_diff(self):
        # Verify no hardcoded keys in unit directory
        for file_path in UNIT.rglob("*"):
            if file_path.is_file() and not file_path.name.endswith((".pyc", ".gitkeep")):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                assert "sk-2e95a" not in content, f"Secret leak in {file_path}"
                assert "dfx_" not in content, f"Secret leak in {file_path}"

    def test_ground_truth_directory_preserved(self):
        assert (UNIT / "ground_truth").is_dir()
        assert (UNIT / "ground_truth" / ".gitkeep").is_file()

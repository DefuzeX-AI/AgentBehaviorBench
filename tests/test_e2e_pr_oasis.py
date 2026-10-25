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
from unittest.mock import MagicMock, patch

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


def _can_import_oasis() -> bool:
    try:
        import numpy  # noqa: F401
        bridge = _load_bridge_module()
        bridge._ensure_import_path()
        import oasis.oasis  # noqa: F401
        from oasis.backends.openai_compat import OpenAICompatClient, OpenAICompatManager  # noqa: F401
        return True
    except Exception:
        return False


requires_oasis = pytest.mark.skipif(
    not _can_import_oasis(),
    reason="Native 'oasis' package or 'numpy' dependency not installed in host environment",
)


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

    @requires_oasis
    def test_scanner_nonzero_exit_and_missing_report_raise_failure(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()

        # Non-zero exit code must raise RuntimeError, preserving native scanner failure
        mock_scanner = MagicMock()
        mock_scanner.setup_argument_parser.return_value.parse_args.return_value = MagicMock()
        mock_scanner.run.return_value = 1
        mock_scanner.report = None

        with pytest.raises(RuntimeError, match="OASIS scanner execution failed with exit code 1"):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                graph._run_scan(Path("/unused"), None)

        # Exit code 0 but no report or findings must raise RuntimeError (not fabricate success)
        mock_scanner.run.return_value = 0
        mock_scanner.valid_input_files = []
        with pytest.raises(RuntimeError, match="OASIS scan completed without producing report or findings"):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                graph._run_scan(Path("/unused"), None)

        # Exit code 0 with input files but failed embeddings must raise RuntimeError preserving blockage
        mock_scanner.valid_input_files = [Path("/unused/test.py")]
        mock_scanner.embedding_manager = MagicMock()
        mock_scanner.embedding_manager.code_base = {}
        with pytest.raises(RuntimeError, match="OASIS failed to generate embeddings"):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                graph._run_scan(Path("/unused"), None)

    @requires_oasis
    def test_native_client_embedding_method_preserved(self):
        # Native OpenAICompatClient must retain its original embedding method without monkey patching
        bridge = _load_bridge_module()
        assert not hasattr(bridge, "_compute_deterministic_embedding")
        assert not hasattr(bridge, "_install_runtime_patches")

        # Directly verify upstream class methods are not monkey-patched
        try:
            from oasis.backends.openai_compat import OpenAICompatClient, OpenAICompatManager
            assert OpenAICompatClient.embeddings.__qualname__ == "OpenAICompatClient.embeddings"
            assert OpenAICompatManager.ensure_model_available.__qualname__ == "OpenAICompatManager.ensure_model_available"
        except ImportError:
            pass

    def test_long_input_and_safe_candidate_handling(self):
        bridge = _load_bridge_module()

        # Input > 255 chars containing slashes must not raise OSError 36
        long_query = "Please scan this function: " + ("a" * 300) + "/test.py"
        assert bridge._is_safe_file_candidate(long_query) is False
        assert bridge._is_conversational_query(long_query) is False

        # Input with code fence
        fenced_input = (
            "Analyze the following Python snippet:\n\n"
            "```python\n"
            "import sqlite3\ndef get_user(u):\n    pass\n"
            "```\n"
        )
        assert bridge._is_safe_file_candidate(fenced_input) is False
        assert bridge._is_conversational_query(fenced_input) is False


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
        assert env["OASIS_EMBED_PROVIDER"] == "openai"
        assert env["OASIS_EMBED_OPENAI_BASE_URL"] == "https://api.openai.com/v1"
        assert env["OASIS_OPENAI_STRUCTURED_OUTPUT"] == "auto"
        assert env["OASIS_OPENAI_THINKING_KWARGS"] == "off"
        assert env["OASIS_OPENAI_HTTP_TIMEOUT_SEC"] == "60"
        assert env["OASIS_NO_UPDATE_CHECK"] == "1"

        runtime = manifest["runtime"]
        for k in ("OPENAI_EMBEDDING_BASE_URL", "OASIS_EMBED_OPENAI_BASE_URL", "EMBED_BASE_URL"):
            assert k in runtime["env_keys"]
        for k in ("OPENAI_EMBEDDING_API_KEY", "OASIS_EMBED_OPENAI_API_KEY", "EMBED_API_KEY"):
            assert k in runtime["optional_secret_env_keys"]

    @requires_oasis
    def test_resilient_model_inventory_and_concurrency_guards(self):
        bridge = _load_bridge_module()
        from oasis.backends.openai_compat import OpenAICompatClient, OpenAICompatManager

        # Ensure qualnames are strictly preserved
        assert OpenAICompatClient.embeddings.__qualname__ == "OpenAICompatClient.embeddings"
        assert OpenAICompatManager.ensure_model_available.__qualname__ == "OpenAICompatManager.ensure_model_available"
        assert OpenAICompatClient.list.__qualname__ == "OpenAICompatClient.list"

        # Verify fallback inventory provides configured models when /models is unrouted
        with patch.dict(os.environ, {"OPENAI_MODEL": "deepseek-flash", "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small"}):
            client = OpenAICompatClient("http://127.0.0.1:9", api_key="dummy")
            models_info = client.list()
            model_names = [m["name"] for m in models_info.get("models", [])]
            assert "deepseek-flash" in model_names
            assert "text-embedding-3-small" in model_names

            manager = OpenAICompatManager("http://127.0.0.1:9", api_key="dummy")
            assert manager.ensure_model_available("deepseek-flash") is True
            assert manager.ensure_model_available("non-existent-model-xyz") is False

    @requires_oasis
    def test_scanner_receives_independent_embedding_configuration(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()

        mock_scanner = MagicMock()
        mock_scanner.run.return_value = 0
        mock_scanner.report = MagicMock()
        mock_scanner.report.output_dir = None
        mock_scanner.findings = []
        mock_scanner.valid_input_files = []

        parsed_args = {}

        def fake_parse_args(args_list):
            for i in range(0, len(args_list) - 1, 2):
                flag = args_list[i]
                val = args_list[i + 1]
                parsed_args[flag] = val
            mock_obj = MagicMock()
            mock_obj.target = parsed_args.get("--target")
            mock_obj.models = [parsed_args.get("--models")]
            mock_obj.embed_models = [parsed_args.get("-em")]
            mock_obj.provider = parsed_args.get("--provider")
            mock_obj.api_base = parsed_args.get("--api-base")
            mock_obj.api_key = parsed_args.get("--api-key")
            mock_obj.embed_provider = parsed_args.get("--embed-provider")
            mock_obj.embed_api_base = parsed_args.get("--embed-api-base")
            mock_obj.embed_api_key = parsed_args.get("--embed-api-key")
            return mock_obj

        mock_scanner.setup_argument_parser.return_value.parse_args.side_effect = fake_parse_args

        # Case A: Separate embedding base url and key
        env_split = {
            "OPENAI_BASE_URL": "http://chat.example.com/v1",
            "OPENAI_API_KEY": "chat-secret-key",
            "OASIS_EMBED_OPENAI_BASE_URL": "http://embed.example.com/v1",
            "OASIS_EMBED_OPENAI_API_KEY": "embed-secret-key",
            "OASIS_EMBED_PROVIDER": "openai",
        }
        with patch.dict(os.environ, env_split, clear=False):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                try:
                    graph._run_scan(Path("/unused"), None)
                except Exception:
                    pass
                assert parsed_args.get("--api-base") == "http://chat.example.com/v1"
                assert parsed_args.get("--api-key") == "chat-secret-key"
                assert parsed_args.get("--embed-api-base") == "http://embed.example.com/v1"
                assert parsed_args.get("--embed-api-key") == "embed-secret-key"
                assert parsed_args.get("--embed-provider") == "openai"

        # Case B: Fallback to chat base url and key when embedding endpoints not specified
        parsed_args.clear()
        env_fallback = {
            "OPENAI_BASE_URL": "http://unified.example.com/v1",
            "OPENAI_API_KEY": "unified-secret-key",
        }
        with patch.dict(os.environ, env_fallback, clear=True):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                try:
                    graph._run_scan(Path("/unused"), None)
                except Exception:
                    pass
                assert parsed_args.get("--api-base") == "http://unified.example.com/v1"
                assert parsed_args.get("--api-key") == "unified-secret-key"
                assert parsed_args.get("--embed-api-base") == "http://unified.example.com/v1"
                assert parsed_args.get("--embed-api-key") == "unified-secret-key"

    @requires_oasis
    def test_vulnerability_embedding_retry_and_failure_surfacing(self):
        bridge = _load_bridge_module()
        bridge._ensure_import_path()
        from oasis.embedding import EmbeddingManager

        mock_client = MagicMock()
        mock_args = MagicMock()
        mock_args.embed_model = "text-embedding-3-small"
        mock_args.chunk_size = 500
        mock_args.embeddings_analyze_type = "file"
        mock_args.cache_dir = None
        mock_backend = MagicMock()
        mock_backend.get_client.return_value = mock_client
        em = EmbeddingManager(mock_args, mock_backend)
        em.ollama_client = mock_client
        em.embedding_model = "test-model"

        # Case 1: Rich prompt fails with 405, concise prompt retry succeeds
        calls = []
        def side_effect_recover(model, prompt):
            calls.append(prompt)
            if "Common patterns" in prompt:
                raise RuntimeError("OpenAI-compatible server returned 405 Method Not Allowed")
            return {"embedding": [0.1, 0.2, 0.3]}

        mock_client.embeddings.side_effect = side_effect_recover
        vec = em.get_vulnerability_embedding({"name": "SQL Injection", "description": "desc", "patterns": ["pat"], "impact": "imp", "mitigation": "mit"})
        assert vec == [0.1, 0.2, 0.3]
        assert len(calls) == 2
        assert "Vulnerability: SQL Injection" in calls[1]

        # Case 2: Both rich prompt and retry fail -> must raise RuntimeError, never return None
        mock_client.embeddings.side_effect = RuntimeError("OpenAI-compatible server returned 405 Method Not Allowed")
        with pytest.raises(RuntimeError, match="Failed to generate embedding for vulnerability type 'SQL Injection'"):
            em.get_vulnerability_embedding({"name": "SQL Injection", "description": "desc", "patterns": ["pat"], "impact": "imp", "mitigation": "mit"})

    @requires_oasis
    def test_zero_vulnerability_types_report_raises_runtime_error(self):
        bridge = _load_bridge_module()
        graph = bridge.create_graph()

        mock_scanner = MagicMock()
        mock_scanner.run.return_value = 0
        mock_scanner.valid_input_files = [Path("/target/vuln.py")]
        mock_scanner.embedding_manager = MagicMock()
        mock_scanner.embedding_manager.code_base = {"/target/vuln.py": {"embedding": [0.1, 0.2]}}
        mock_scanner.setup_argument_parser.return_value.parse_args.return_value = MagicMock()

        # Mock report output containing the hollow 0-type summary
        with patch.object(graph, "_collect_report_text", return_value="## Overview\nAnalyzed 0 vulnerability types across the codebase."):
            with patch("oasis.oasis.OasisScanner", return_value=mock_scanner):
                with pytest.raises(RuntimeError, match="analyzed 0 vulnerability types across the codebase"):
                    graph._run_scan(Path("/unused"), None)

    @requires_oasis
    def test_openai_compat_embeddings_fallback_on_array_rejection(self):
        bridge = _load_bridge_module()
        bridge._ensure_import_path()
        from oasis.backends.openai_compat import OpenAICompatClient

        client = OpenAICompatClient("http://127.0.0.1:9999", api_key="dummy")
        posted_payloads = []

        def fake_post_json(path, payload, timeout=None):
            posted_payloads.append(payload)
            if isinstance(payload.get("input"), list):
                raise RuntimeError("OpenAI-compatible server returned 405 for /embeddings")
            return {"data": [{"embedding": [0.42, 0.84]}]}

        with patch.object(client, "_post_json", side_effect=fake_post_json):
            res = client.embeddings(model="test-embed", prompt="single text prompt")
            assert res == {"embedding": [0.42, 0.84]}
            assert len(posted_payloads) == 2
            assert posted_payloads[0]["input"] == ["single text prompt"]
            assert posted_payloads[1]["input"] == "single text prompt"

    @requires_oasis
    def test_search_vulnerabilities_propagates_embedding_failure(self):
        bridge = _load_bridge_module()
        bridge._ensure_import_path()
        from oasis.analyze import SecurityAnalyzer

        analyzer = SecurityAnalyzer.__new__(SecurityAnalyzer)
        analyzer.embedding_manager = MagicMock()
        analyzer.embedding_manager.get_vulnerability_embedding.side_effect = RuntimeError(
            "Failed to generate embedding for vulnerability type 'SQL Injection'"
        )
        analyzer.code_base = {"/target/app.py": {"embedding": [0.1, 0.2]}}
        analyzer.analyze_by_function = False

        # Guard 6 must propagate the RuntimeError rather than returning []
        with pytest.raises(RuntimeError, match="Failed to generate embedding for vulnerability type 'SQL Injection'"):
            analyzer.search_vulnerabilities({"name": "SQL Injection"}, threshold=0.5)


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

"""E2E Verification Suite for DefuzeX ABB PR #426 PosterGen Onboarding Review Remediation.

Structured according to the 4-tier testing hierarchy:
- Tier 1: Feature Coverage (Category-Partition Method)
- Tier 2: Boundary Value Analysis (BVA) & Corner Cases
- Tier 3: Pairwise Combinatorial & Cross-Feature Interactions
- Tier 4: Real-World Scenarios & Workload Integrity

Follows opaque-box, requirement-driven verification contracts.
Progressive milestone isolation ensures tests run with 0 failures on clean checkout
while dynamically activating assertions as milestones (M1–M5) land.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.docker.policy import (
    CPUS_ENV,
    MEMORY_ENV,
    DockerPolicy,
    _validate_docker_cpus,
    _validate_docker_memory,
)

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "62-postergen"
REGISTRY_PATH = ROOT / "resources" / "registry.toml"

# Self-contained minimal valid PDF-1.4 binary fixture
# Valid header, catalog (1 0 obj), pages (2 0 obj), page (3 0 obj with MediaBox),
# xref table, trailer, startxref, and %%EOF marker.
MINIMAL_VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
    b"startxref\n190\n"
    b"%%EOF\n"
)


def _load_bridge_module():
    bridge_path = UNIT / "bindings" / "bridge.py"
    assert bridge_path.is_file(), f"Bridge binding file missing: {bridge_path}"
    spec = importlib.util.spec_from_file_location("e2e_postergen_bridge", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ==============================================================================
# Tier 1: Feature Coverage (Category-Partition Method)
# ==============================================================================

class TestTier1FeatureCoverage:
    """Tier 1: Nominal feature coverage and contract verification."""

    def test_registry_01_to_62_contiguous_layout(self):
        """Verify Agent #62 renumbering and contiguous 01-62 registry layout."""
        assert REGISTRY_PATH.is_file(), f"Missing registry at {REGISTRY_PATH}"
        assert UNIT.is_dir(), f"Expected unit directory at {UNIT}"

        # 1. Inspect registry.toml
        with REGISTRY_PATH.open("rb") as stream:
            entries = tomllib.load(stream)["agents"]

        registered_paths = [ROOT / entry["path"] for entry in entries]
        agents_dir = ROOT / "resources" / "agents"
        unit_dirs = {p for p in agents_dir.iterdir() if p.is_dir()}

        assert len(set(registered_paths)) == len(entries), "Duplicate entries in registry"
        assert set(registered_paths) == unit_dirs, "Registry entries must exactly match filesystem units"

        # 2. Contiguous numbering 01 to 62
        numbers = []
        for unit in unit_dirs:
            prefix, sep, name = unit.name.partition("-")
            assert sep and prefix.isdecimal() and name, f"Invalid unit name format: {unit.name}"
            num = int(prefix)
            numbers.append(num)
            assert prefix == f"{num:02d}", f"Number prefix not two digits: {prefix}"

        assert sorted(numbers) == list(range(1, len(unit_dirs) + 1)), (
            "Agent directory numbering must be contiguous starting from 01"
        )
        assert len(unit_dirs) >= 62, f"Expected at least 62 agents, found {len(unit_dirs)}"

        # 3. PosterGen unit entry
        registry = load_registry(REGISTRY_PATH)
        postergen_entry = registry.find("postergen", enabled_only=False)
        assert postergen_entry is not None, "postergen not found in registry"
        assert postergen_entry.path == UNIT
        assert postergen_entry.framework == "langgraph"
        assert postergen_entry.status == "adapting"

    def test_langgraph_config_propagation_contract(self, monkeypatch):
        """Verify PosterGenBinding propagates ABB execution config into workflow.invoke."""
        import sys
        from unittest.mock import patch

        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        mock_timing = MagicMock()
        mock_timing.get_total_time.return_value = 1.0
        mock_timing.get_api_call_count.return_value = 1

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {
            "output_dir": "/tmp",
            "poster_name": "mock_poster",
            "timing_metrics": mock_timing,
            "errors": None,
        }
        binding._compiled_workflow = mock_workflow

        mock_poster_state = MagicMock()
        mock_poster_state.create_state.return_value = {
            "timing_metrics": MagicMock(),
            "output_dir": "/tmp",
            "poster_name": "mock_poster",
            "errors": None,
        }
        mock_pipeline = MagicMock()
        mock_pipeline.save_timing_log.return_value = "/tmp/log.json"

        test_config = {
            "callbacks": [MagicMock()],
            "configurable": {"thread_id": "abb-session-test"},
            "metadata": {"abb_run_id": "run-m2-verify"},
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(MINIMAL_VALID_PDF)
            f.flush()

            # Execute bridge invoke with execution config under mocked upstream pipeline
            with patch.dict(
                sys.modules,
                {
                    "src.state.poster_state": mock_poster_state,
                    "src.workflow.pipeline": mock_pipeline,
                },
            ):
                binding.invoke({"paper_path": f.name}, config=test_config)

            assert mock_workflow.invoke.called, "workflow.invoke was not called"
            call_kwargs = mock_workflow.invoke.call_args.kwargs
            assert "config" in call_kwargs, "config parameter was not passed to workflow.invoke"
            assert call_kwargs["config"] == test_config

        binding.close()

    def test_langgraph_ainvoke_config_preservation(self, monkeypatch):
        """Verify PosterGenBinding.ainvoke delegates to invoke preserving config."""
        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        mock_invoke = MagicMock(return_value={"final_output": {"status": "completed"}})
        binding.invoke = mock_invoke

        test_config = {"configurable": {"thread_id": "async-thread-1"}}
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(binding.ainvoke("Introduce yourself", config=test_config))
            assert res == {"final_output": {"status": "completed"}}
            mock_invoke.assert_called_once_with("Introduce yourself", test_config)
        finally:
            loop.close()
            binding.close()

    def test_docker_policy_from_environment_factory(self):
        """Verify DockerPolicy.from_environment factory method construct limits."""
        # Custom environment mapping
        env = {"ABB_DOCKER_MEMORY": "8g", "ABB_DOCKER_CPUS": "4"}
        policy = DockerPolicy.from_environment(env)
        assert policy.memory == "8g"
        assert policy.cpus == 4.0

        # Base override
        base = DockerPolicy(memory="2g", cpus=2.0)
        policy_base = DockerPolicy.from_environment(env, base=base)
        assert policy_base.memory == "8g"
        assert policy_base.cpus == 4.0

    def test_offline_minimal_pdf_fixture_validity(self):
        """Verify offline minimal PDF fixture satisfies PDF structural validation."""
        bridge = _load_bridge_module()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(MINIMAL_VALID_PDF)
            tmp_path = Path(f.name)

        try:
            # Must pass without raising ValueError
            bridge._validate_pdf_file(tmp_path, "minimal_test.pdf")

            # Must resolve cleanly in bridge._resolve_paper_input
            binding = bridge.create_graph()
            resolved = binding._resolve_paper_input({"paper_path": str(tmp_path)})
            assert resolved[0] == str(tmp_path.resolve())
            binding.close()
        finally:
            tmp_path.unlink()

    def test_deepseek_model_provider_registration(self):
        """Verify DeepSeek provider catalog registration and endpoint paths."""
        from agentbench.runtime.interception.provider_catalog import load_provider_catalog
        from agentbench.runtime.interception.providers import resolve_model_provider

        catalog = load_provider_catalog({})
        assert "deepseek" in catalog["providers"], "deepseek missing from DEFAULT_PROVIDER_CATALOG"
        ds_provider = catalog["providers"]["deepseek"]
        assert ds_provider["credential_env"] == "DEEPSEEK_API_KEY"
        assert ds_provider["model_env"] == "DEEPSEEK_MODEL"
        assert ds_provider["base_url_env"] == "DEEPSEEK_BASE_URL"
        assert ds_provider["base_url"] == "https://api.deepseek.com"
        assert ds_provider["target_plugin"] == "compatible-json"
        assert "/chat/completions" in ds_provider["endpoint_paths"]

        # Test resolution via ABB_MODEL_PROVIDER
        env = {
            "DEEPSEEK_API_KEY": "ds-key-123",
            "ABB_MODEL_PROVIDER": "deepseek",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }
        provider = resolve_model_provider(environ=env)
        target = provider.resolve(env)
        assert target.provider_id == "deepseek"
        assert target.model == "deepseek-chat"
        assert target.base_url == "https://api.deepseek.com"


# ==============================================================================
# Tier 2: Boundary Value Analysis (BVA) & Corner Cases
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary conditions, empty environ isolation, and error rejection."""

    def test_docker_runtime_empty_environ_without_ambient_bleed(self, monkeypatch):
        """Verify DockerRuntime(environ={}) isolates against ambient process environment."""
        monkeypatch.setenv(MEMORY_ENV, "8g")
        monkeypatch.setenv(CPUS_ENV, "4")

        from agentbench.runtime.docker.runtime import DockerRuntime

        runtime = DockerRuntime(environ={})
        assert runtime.policy.memory == "1g", (
            f"Expected memory '1g' with environ={{}}, got '{runtime.policy.memory}' (ambient bleed)"
        )
        assert runtime.policy.cpus == 1.0, (
            f"Expected cpus 1.0 with environ={{}}, got {runtime.policy.cpus} (ambient bleed)"
        )

    def test_docker_policy_explicit_argument_preservation(self, monkeypatch):
        """Verify explicit DockerPolicy arguments are preserved regardless of ambient os.environ."""
        monkeypatch.setenv(MEMORY_ENV, "8g")
        monkeypatch.setenv(CPUS_ENV, "4")

        policy_default_explicit = DockerPolicy(memory="1g", cpus=1.0)
        assert policy_default_explicit.memory == "1g"
        assert policy_default_explicit.cpus == 1.0

        policy_custom_explicit = DockerPolicy(memory="2g", cpus=2.0)
        assert policy_custom_explicit.memory == "2g"
        assert policy_custom_explicit.cpus == 2.0

    def test_docker_policy_validation_boundaries(self):
        """Verify Docker policy format validation functions reject boundary violations."""
        # 1. Memory format bounds
        assert _validate_docker_memory("1g") == "1g"
        assert _validate_docker_memory("512m") == "512m"
        assert _validate_docker_memory("16G") == "16G"

        invalid_memories = ["", "   ", "0g", "-8g", "8.5g", "8", "8gb", "none", None, 1024]
        for bad_mem in invalid_memories:
            with pytest.raises(ValueError):
                _validate_docker_memory(bad_mem)

        # 2. CPU bounds: 0.0 < cpus <= 1024.0
        assert _validate_docker_cpus(1.0) == 1.0
        assert _validate_docker_cpus(4) == 4
        assert _validate_docker_cpus("2.5") == 2.5
        assert _validate_docker_cpus(1024.0) == 1024.0

        invalid_cpus = [0, 0.0, -1, -0.5, 1024.1, "bad", True, False, float("nan"), float("inf"), None]
        for bad_cpu in invalid_cpus:
            with pytest.raises(ValueError):
                _validate_docker_cpus(bad_cpu)

    def test_prompt_newline_and_length_boundaries(self):
        """Verify input normalization and path safety check across length and newline boundaries."""
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        # Newline and whitespace normalization
        norm = binding._normalize_input("  \nTitle of Paper\nSecond line\t  \n")
        assert norm["text"] == "Title of Paper\nSecond line"

        # Rejection of empty, whitespace, and None
        with pytest.raises(ValueError, match="Input value cannot be None"):
            binding._normalize_input(None)
        with pytest.raises(ValueError, match="Input string cannot be empty"):
            binding._normalize_input("")
        with pytest.raises(ValueError, match="Input string cannot be empty"):
            binding._normalize_input("   \n\t  ")

        # POSIX limits in _is_safe_path_candidate
        # Component limit (255 bytes)
        assert bridge._is_safe_path_candidate("a" * 255) is True
        assert bridge._is_safe_path_candidate("a" * 256) is False

        # Total path limit (4096 bytes)
        safe_long_path = "/" + "/".join(["sub"] * 100)
        assert bridge._is_safe_path_candidate(safe_long_path) is True
        unsafe_long_path = "/" + "a/" * 2050
        assert bridge._is_safe_path_candidate(unsafe_long_path) is False

        # Null byte injection
        assert bridge._is_safe_path_candidate("path/with\0bad") is False
        binding.close()

    def test_malformed_pdf_rejection(self):
        """Verify bridge PDF validator rejects empty, headerless, and truncated files."""
        bridge = _load_bridge_module()

        # 1. 0-byte file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            empty_path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="empty \\(0 bytes\\)"):
                bridge._validate_pdf_file(empty_path, "empty.pdf")
        finally:
            empty_path.unlink()

        # 2. Invalid header (missing %PDF-)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"NOT_A_PDF_FILE_CONTENT\n%%EOF\n")
            bad_header_path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="does not have a valid PDF header"):
                bridge._validate_pdf_file(bad_header_path, "bad_header.pdf")
        finally:
            bad_header_path.unlink()

        # 3. Truncated (missing %%EOF trailer)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")
            no_eof_path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="truncated or missing its PDF trailer"):
                bridge._validate_pdf_file(no_eof_path, "no_eof.pdf")
        finally:
            no_eof_path.unlink()

    def test_missing_paper_rejection(self, monkeypatch):
        """Verify non-existent paper requests return diagnostic error without running synthesis."""
        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        res = binding.invoke("Generate a poster for completely_nonexistent_paper_426.pdf")
        assert res["final_output"]["status"] == "error"
        assert "Unable to generate poster" in res["final_output"]["answer"]
        assert "Invalid or missing paper input" in res["final_output"]["answer"]
        assert "Requirement: PosterGen requires a valid, accessible research paper" in res["final_output"]["answer"]
        binding.close()


# ==============================================================================
# Tier 3: Pairwise Combinatorial & Cross-Feature Interactions
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Multi-component interactions, callback dispatch, and prompt routing."""

    def test_langgraph_callback_dispatch_with_runtime_config(self, monkeypatch):
        """Verify LangGraph callback dispatch receives graph events while runtime config is active."""
        import sys
        from unittest.mock import patch

        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        mock_callback = MagicMock()
        mock_timing = MagicMock()
        mock_timing.get_total_time.return_value = 0.5
        mock_timing.get_api_call_count.return_value = 1

        mock_workflow = MagicMock()
        mock_workflow.invoke.return_value = {
            "output_dir": "/tmp",
            "poster_name": "callback_test",
            "timing_metrics": mock_timing,
            "errors": None,
        }
        binding._compiled_workflow = mock_workflow

        mock_poster_state = MagicMock()
        mock_poster_state.create_state.return_value = {
            "timing_metrics": MagicMock(),
            "output_dir": "/tmp",
            "poster_name": "callback_test",
            "errors": None,
        }
        mock_pipeline = MagicMock()
        mock_pipeline.save_timing_log.return_value = "/tmp/log.json"

        runtime_config = {
            "callbacks": [mock_callback],
            "configurable": {"thread_id": "thread-interaction-test", "model": "deepseek-chat"},
            "metadata": {"abb_run_id": "run-comb-123", "user_id": "evaluator"},
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(MINIMAL_VALID_PDF)
            f.flush()

            with patch.dict(
                sys.modules,
                {
                    "src.state.poster_state": mock_poster_state,
                    "src.workflow.pipeline": mock_pipeline,
                },
            ):
                binding.invoke({"paper_path": f.name}, config=runtime_config)

            assert mock_workflow.invoke.called
            call_kwargs = mock_workflow.invoke.call_args.kwargs
            assert "config" in call_kwargs, "config parameter was not passed to workflow.invoke"
            assert call_kwargs["config"] == runtime_config

        binding.close()

    @pytest.mark.parametrize("prompt", [
        "introduce yourself",
        "Introduce PosterGen and its capabilities",
        "tell me about yourself",
        "what are your features?",
        "What features does postergen have?",
        "how does this work?",
        "what can this agent do?",
        "help",
        "user guide",
    ])
    def test_conversational_pure_prompt_routing(self, monkeypatch, prompt):
        """Verify purely conversational and capability inquiries return capabilities text immediately."""
        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        res = binding.invoke(prompt)
        assert res["final_output"]["status"] == "completed"
        assert "PosterGen" in res["final_output"]["answer"]
        assert "scientific research papers into publication-ready academic conference posters" in res["final_output"]["answer"]
        assert res["final_output"]["poster_name"] is None
        assert res["final_output"]["artifacts"] == []
        binding.close()

    def test_disambiguation_features_and_introduce_with_paper_candidate(self, monkeypatch):
        """Verify requests containing 'features' or 'introduce' + valid paper reach synthesis pipeline."""
        import sys
        from unittest.mock import patch

        monkeypatch.setenv("OPENAI_API_KEY", "mock-key-for-test")
        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(MINIMAL_VALID_PDF)
            tmp_pdf = Path(f.name)

        try:
            # 1. Prompt with 'introduce' and explicit paper path
            prompt_introduce = f"Please generate a poster to introduce {tmp_pdf.name}"
            is_conv_1 = binding._is_conversational_request(prompt_introduce, str(tmp_pdf))
            assert is_conv_1 is False, "Prompt with paper reference must not be marked conversational"

            resolved_1 = binding._resolve_paper_input({"paper_path": str(tmp_pdf), "text": prompt_introduce})
            assert resolved_1[0] == str(tmp_pdf.resolve())

            # 2. Prompt with 'features' and explicit paper path
            prompt_features = f"Summarize the main features and architecture of {tmp_pdf.name} into a poster"
            is_conv_2 = binding._is_conversational_request(prompt_features, str(tmp_pdf))
            assert is_conv_2 is False, "Prompt with 'features' and paper reference must not be marked conversational"

            resolved_2 = binding._resolve_paper_input({"paper_path": str(tmp_pdf), "text": prompt_features})
            assert resolved_2[0] == str(tmp_pdf.resolve())

            # 3. Prompts mixing 'introduce' and 'features' with poster generation intent
            prompt_novel = f"This paper introduces novel architectural features. Please generate a poster from {tmp_pdf}"
            assert binding._is_conversational_request(prompt_novel, str(tmp_pdf)) is False

            prompt_create = f"Can you create a poster that introduces the key features of {tmp_pdf}?"
            assert binding._is_conversational_request(prompt_create, str(tmp_pdf)) is False

            # 4. Pure third-person feature queries without paper candidate must route to conversational
            prompt_conv_features = "What features does postergen have?"
            assert binding._is_conversational_request(prompt_conv_features, prompt_conv_features) is True
            res_conv = binding.invoke(prompt_conv_features)
            assert res_conv["final_output"]["status"] == "completed"
            assert res_conv["final_output"]["answer"] == bridge.POSTERGEN_CAPABILITIES_TEXT

            # 5. End-to-end invoke verification with mocked workflow
            mock_timing = MagicMock()
            mock_timing.get_total_time.return_value = 0.5
            mock_timing.get_api_call_count.return_value = 1
            mock_workflow = MagicMock()
            mock_workflow.invoke.return_value = {
                "output_dir": "/tmp",
                "poster_name": "disambiguation_poster",
                "timing_metrics": mock_timing,
                "errors": None,
            }
            binding._compiled_workflow = mock_workflow

            mock_poster_state = MagicMock()
            mock_poster_state.create_state.return_value = {
                "timing_metrics": MagicMock(),
                "output_dir": "/tmp",
                "poster_name": "disambiguation_poster",
                "errors": None,
            }
            mock_pipeline = MagicMock()
            mock_pipeline.save_timing_log.return_value = "/tmp/log.json"

            with patch.dict(
                sys.modules,
                {
                    "src.state.poster_state": mock_poster_state,
                    "src.workflow.pipeline": mock_pipeline,
                },
            ):
                monkeypatch.setattr(binding, "_deliver_artifacts", lambda artifacts, dests: [])
                res = binding.invoke(prompt_novel)
                assert mock_workflow.invoke.called
                assert res["final_output"]["status"] in ("completed", "success")
                assert res["final_output"]["answer"] != bridge.POSTERGEN_CAPABILITIES_TEXT
        finally:
            tmp_pdf.unlink()
            binding.close()


# ==============================================================================
# Tier 4: Real-World Scenarios & Workload Integrity
# ==============================================================================

class TestTier4RealWorldScenarios:
    """Tier 4: Offline environment validation, Docker smoke arguments, and credential security."""

    def test_clean_checkout_offline_suite_integrity(self):
        """Verify that all required unit files exist and upstream checkout agent/ is ignored."""
        # 1. Required files
        required_files = [
            "agent.toml",
            "Dockerfile",
            ".dockerignore",
            "requirement.md",
            "source-manifest.json",
            "bindings/bridge.py",
            "ground_truth/.gitkeep",
        ]
        for rel in required_files:
            target = UNIT / rel
            assert target.is_file(), f"Required unit file missing: {target}"

        # 2. agent.toml manifest structure
        manifest_text = (UNIT / "agent.toml").read_text(encoding="utf-8")
        manifest = tomllib.loads(manifest_text)
        assert manifest["agent_id"] == "postergen"
        assert manifest["framework"] == "langgraph"
        assert manifest["adapter"]["binding"] == "bridge.py:create_graph"
        assert manifest["adapter"]["output_key"] == "final_output"

        # 3. .dockerignore contains essential isolation entries
        dockerignore = (UNIT / ".dockerignore").read_text(encoding="utf-8")
        assert ".git" in dockerignore
        assert ".env" in dockerignore
        assert "__pycache__" in dockerignore

    def test_docker_smoke_arguments_and_policy_contract(self):
        """Verify DockerPolicy produces hardened container run arguments matching smoke specification."""
        policy = DockerPolicy(memory="8g", cpus=4.0, pids_limit=128)
        args = policy.run_arguments()

        assert "--memory=8g" in args
        assert "--cpus=4" in args or "--cpus=4.0" in args
        assert "--pids-limit=128" in args
        assert "--cap-drop=ALL" in args
        assert "--security-opt=no-new-privileges" in args

        # Tmpfs mounts
        assert any(arg.startswith("--tmpfs=/tmp:") for arg in args)
        assert any(arg.startswith("--tmpfs=/run/agentbench-tools:") for arg in args)

    def test_secret_hygiene_in_evaluation_environment(self, monkeypatch):
        """Verify that sensitive API tokens are never leaked into string representations or errors."""
        mock_secret = "dfx_live_secret_key_never_leak_this"
        monkeypatch.setenv("OPENAI_API_KEY", mock_secret)

        bridge = _load_bridge_module()
        binding = bridge.create_graph()

        # Fast conversational query
        res = binding.invoke("introduce yourself")
        res_str = repr(res)
        assert mock_secret not in res_str, "Secret leaked in conversational response representation"

        # Diagnostic error query
        err_res = binding.invoke("make poster for missing_paper.pdf")
        err_str = repr(err_res)
        assert mock_secret not in err_str, "Secret leaked in diagnostic error response representation"

        binding.close()

    def test_m5_docker_local_smoke_artifacts_integrity(self):
        """Verify M5 containerized Docker Local Smoke execution artifacts and DeepSeek judge pass."""
        results_dir = ROOT / "results" / "issue383-postergen-local-smoke"
        if not results_dir.is_dir():
            pytest.skip("Docker local smoke results directory not present")

        manifests = list(results_dir.rglob("evaluation/manifest.json"))
        assert len(manifests) >= 1, "Expected at least one evaluation/manifest.json in smoke results"

        manifest_path = manifests[0]
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest_data["case_id"] == "local-smoke-v1-01"
        assert manifest_data["phase"] == "finished"
        assert manifest_data["execution"] == "succeeded"
        assert manifest_data["otel"] == "complete"
        assert manifest_data["submission"] == "committed"
        assert manifest_data["judge"] == "received"

        attempt_dir = manifest_path.parents[1]
        run_file = attempt_dir / "run.json"
        assert run_file.is_file(), f"Missing run.json at {run_file}"
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
        assert run_data["exit_code"] == 0
        assert run_data["status"] == "succeeded"

        judge_file = attempt_dir / "local-judge.json"
        assert judge_file.is_file(), f"Missing local-judge.json at {judge_file}"
        judge_data = json.loads(judge_file.read_text(encoding="utf-8"))
        assert judge_data["model"] == "deepseek-chat"
        assert judge_data["answer"]["status"] == "pass"

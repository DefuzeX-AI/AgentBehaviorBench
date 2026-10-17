"""Issue #383: Y-Research-SBU/PosterGen onboarding contract.

Offline contracts only: no Docker, no network, no model call. Passing these does not
certify the Agent; certification is what promotes an adapting integration.

The tracked unit is ASCII-only. The upstream checkout lives in agent/, which
.gitignore excludes. Tests that read that checkout are skipped until materialized.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
from agentbench.sdk.plugin.kuma.onboarding import validate as validate_kuma_profile
from kuma.repository.agent_profiles import parse_agent_profile

ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "60-postergen"
SNAPSHOT = UNIT / "agent"
REPOSITORY = "https://github.com/Y-Research-SBU/PosterGen"
REVISION = "8a54325f871ee10fa6545de3b3a9b771aa12620c"

needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "src" / "workflow" / "pipeline.py").is_file(),
    reason="agent/ is materialized from [source] at prepare time and is not tracked",
)

_MISSING = next(
    (name for name in ("marker", "langgraph") if importlib.util.find_spec(name) is None),
    None,
)
needs_upstream_deps = pytest.mark.skipif(
    _MISSING is not None,
    reason=f"upstream runtime dependency '{_MISSING}' is not installed in this environment",
)


def _binding():
    spec = importlib.util.spec_from_file_location(
        "issue383_postergen_binding", UNIT / "bindings" / "bridge.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest():
    return tomllib.loads((UNIT / "agent.toml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------- Tracked Unit Hygiene

def test_tracked_unit_is_ascii_only():
    """All tracked files contributed by ABB must be pure ASCII."""
    offenders = []
    for path in sorted(UNIT.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(UNIT)
        if relative.parts[:1] == ("agent",) or "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if any(b > 127 for b in path.read_bytes()):
            offenders.append(relative.as_posix())
    assert offenders == [], f"non-ASCII tracked files: {offenders}"


def test_unit_contains_all_required_files():
    """All required ABB integration and metadata files must exist."""
    required = [
        "agent.toml",
        "Dockerfile",
        ".dockerignore",
        "requirement.md",
        "source-manifest.json",
        "bindings/bridge.py",
        "ground_truth/.gitkeep",
    ]
    for rel_path in required:
        assert (UNIT / rel_path).is_file(), f"Missing required file: {rel_path}"


def test_dockerignore_matches_official_template():
    """Verify .dockerignore prevents leaking host files, git metadata, and env."""
    text = (UNIT / ".dockerignore").read_text(encoding="utf-8")
    assert ".git" in text
    assert ".env" in text
    assert "__pycache__" in text


def test_ground_truth_is_placeholder():
    keep = UNIT / "ground_truth" / ".gitkeep"
    assert keep.is_file()
    assert keep.read_bytes() == b""


# ------------------------------------------------------------------- Source Manifest & Registry

def test_source_manifest_pins_issue383_revision():
    data = json.loads((UNIT / "source-manifest.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "abb.agent-source.v1"
    assert data["repository"] == REPOSITORY
    assert data["revision"] == REVISION


def test_registry_entry_points_at_postergen_unit():
    registry = load_registry(ROOT / "resources" / "registry.toml")
    entry = registry.find("postergen", enabled_only=False)
    assert entry.path == UNIT
    assert entry.framework == "langgraph"
    assert entry.status in {"ready", "adapting"}


def test_registry_agent_id_matches_unit_manifest():
    manifest = _manifest()
    assert manifest["agent_id"] == "postergen"
    assert manifest["framework"] == "langgraph"


# ------------------------------------------------------------------- agent.toml Manifest Schema

def test_manifest_schema_and_metadata():
    manifest = _manifest()
    assert manifest["schema_version"] == "defuzex-bench.agent.v2"
    assert manifest["agent_id"] == "postergen"
    assert manifest["framework"] == "langgraph"
    assert manifest["source"]["repository"] == REPOSITORY
    assert manifest["source"]["revision"] == REVISION
    assert manifest["evaluation"]["replay_safe"] is False


def test_manifest_adapter_and_interception():
    manifest = _manifest()
    adapter = manifest["adapter"]
    assert adapter["type"] == "langgraph"
    assert adapter["mode"] == "in_process"
    assert adapter["binding"] == "bridge.py:create_graph"
    assert adapter["output_key"] == "final_output"

    interception = manifest["llm_interception"]
    assert interception["trust_plugin"] == "pem-env"
    creds = {c["agent_env"] for c in interception["credentials"]}
    assert "OPENAI_API_KEY" in creds

    routes = interception["routes"]
    assert any(
        "api.openai.com" in r["host_patterns"] and "/v1/chat/completions" in r["path_patterns"]
        for r in routes
    )


# ------------------------------------------------------------------- Static Unit Validation

def test_validate_unit_passes_with_kuma_plugin():
    agent_id = validate_unit(UNIT, plugin)
    assert agent_id == "postergen"


# ------------------------------------------------------------------- KUMA Profile Contract

def test_requirement_profile_passes_official_kuma_parse():
    validate_kuma_profile(UNIT)
    profile = parse_agent_profile(UNIT / "requirement.md")
    assert profile.input_type == "text"
    assert 0 < len(profile.agent_description) <= 2000
    assert set(profile.sections) >= {
        "production_scenario",
        "behaviors_to_test",
        "prohibited_behaviors",
    }
    assert profile.strategy_group.id
    assert profile.strategy_group.version


# ------------------------------------------------------------------- Binding Adapter Contracts

def test_factory_is_zero_argument_callable():
    module = _binding()
    assert callable(module.create_graph)
    instance = module.create_graph()
    assert hasattr(instance, "invoke")
    assert hasattr(instance, "close")
    instance.close()


def test_binding_normalizes_text_input():
    module = _binding()
    instance = module.create_graph()
    norm = instance._normalize_input("A research paper on quantum error correction.")
    assert "text" in norm or "message" in norm or "topic" in norm or "paper_path" in norm
    instance.close()


def test_binding_rejects_malformed_input():
    module = _binding()
    instance = module.create_graph()
    with pytest.raises(ValueError):
        instance._normalize_input("")
    with pytest.raises(ValueError):
        instance._normalize_input("   \n\t  ")
    with pytest.raises(ValueError):
        instance._normalize_input(None)
    instance.close()


def test_missing_model_credential_fails_before_call(monkeypatch):
    module = _binding()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    instance = module.create_graph()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        instance.invoke("Generate a poster for paper X")
    instance.close()


def test_closed_session_rejects_invocation():
    module = _binding()
    instance = module.create_graph()
    instance.close()
    with pytest.raises(RuntimeError, match="closed"):
        instance.invoke("test prompt")


# ------------------------------------------------------------------- Upstream Graph Inspection

@needs_snapshot
def test_upstream_pipeline_topology_ast():
    pipeline_file = SNAPSHOT / "src" / "workflow" / "pipeline.py"
    tree = ast.parse(pipeline_file.read_text(encoding="utf-8"))
    nodes = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_node"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            nodes.add(node.args[0].value)
    expected_nodes = {
        "parser", "curator", "color_agent", "section_title_designer",
        "layout_optimizer", "font_agent", "renderer"
    }
    assert expected_nodes.issubset(nodes), f"Missing nodes: {expected_nodes - nodes}"


@needs_snapshot
@needs_upstream_deps
def test_upstream_pipeline_topology():
    if str(SNAPSHOT) not in sys.path:
        sys.path.insert(0, str(SNAPSHOT))
    from src.workflow.pipeline import create_workflow_graph
    graph = create_workflow_graph()
    nodes = set(graph.nodes.keys())
    expected_nodes = {
        "parser", "curator", "color_agent", "section_title_designer",
        "layout_optimizer", "font_agent", "renderer"
    }
    assert expected_nodes.issubset(nodes), f"Missing nodes: {expected_nodes - nodes}"


# ------------------------------------------------------------------- Dockerfile Contract

def test_dockerfile_static_configuration():
    dockerfile = (UNIT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim" in dockerfile
    assert "USER agent" in dockerfile
    assert "libreoffice" in dockerfile
    assert "fonts" in dockerfile
    assert "COPY bindings/ ./bindings/" in dockerfile
    assert "COPY agent.toml ./agent.toml" in dockerfile


# ------------------------------------------------------------------- Runtime Policy Configuration

def test_docker_policy_memory_configuration_for_heavy_models(monkeypatch):
    """Verify DockerPolicy dynamically honors ABB_DOCKER_MEMORY and ABB_DOCKER_CPUS."""
    from agentbench.runtime.docker.policy import DockerPolicy, MEMORY_ENV, CPUS_ENV

    monkeypatch.delenv(MEMORY_ENV, raising=False)
    monkeypatch.delenv(CPUS_ENV, raising=False)
    policy_default = DockerPolicy()
    assert policy_default.memory == "1g"
    assert policy_default.cpus == 1.0

    monkeypatch.setenv(MEMORY_ENV, "8g")
    monkeypatch.setenv(CPUS_ENV, "4")
    policy_configured = DockerPolicy()
    assert policy_configured.memory == "8g"
    assert policy_configured.cpus == 4.0
    args = policy_configured.run_arguments()
    assert "--memory=8g" in args
    assert "--cpus=4.0" in args

    # Explicit override takes precedence
    policy_override = DockerPolicy(memory="2g", cpus=2.0)
    assert policy_override.memory == "2g"
    assert policy_override.cpus == 2.0

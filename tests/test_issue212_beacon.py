"""Issue #212: 123-qw-as/Beacon (Math Modeling Agent) onboarding contract.

Offline contracts only: no Docker, no network, no model call. Passing these does not
certify the Agent; certification is what promotes an ``adapting`` integration.

The tracked unit is ASCII-only. The upstream checkout lives in ``agent/``, which
``.gitignore`` excludes ("Runtime source/install materialization"): ABB restores it from
the ``[source]`` repository and revision in ``agent.toml`` before an evaluation opens.
The contracts that read that checkout are skipped until it is materialized, so this file
passes both in a fresh clone and on a machine that has run a build.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "46-beacon"
SNAPSHOT = UNIT / "agent"
REPOSITORY = "https://github.com/123-qw-as/Beacon"
REVISION = "36b0b7de6774bc619dc39a80a00a41639909d7e9"

# Reading the checkout needs it on disk; a fresh clone does not have it.
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "src" / "math_agent" / "graph.py").is_file(),
    reason="agent/ is materialized from [source] at prepare time and is not tracked",
)

# Importing the upstream graph pulls in langgraph; the binding module itself does not
# (its imports of math_agent are deferred to first use). A checkout that has not been
# built cannot exercise the graph-construction contracts; they are skipped with a reason
# rather than stubbed, because a stubbed graph would not be the graph.
needs_langgraph = pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="upstream runtime dependency 'langgraph' is not installed in this environment",
)


def _binding():
    spec = importlib.util.spec_from_file_location(
        "issue212_beacon_binding", UNIT / "bindings" / "bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest():
    return tomllib.loads((UNIT / "agent.toml").read_text())


# ------------------------------------------------------------------- tracked unit


def test_tracked_unit_is_ascii_only():
    offenders = []
    for path in sorted(UNIT.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(UNIT)
        if relative.parts[:1] == ("agent",):
            continue  # the upstream checkout is restored, not tracked
        if any(b > 127 for b in path.read_bytes()):
            offenders.append(relative.as_posix())
    assert offenders == [], f"non-ASCII tracked files: {offenders}"


def test_ground_truth_is_a_placeholder():
    keep = UNIT / "ground_truth" / ".gitkeep"
    assert keep.is_file()
    assert keep.read_bytes() == b""


def test_dockerignore_matches_the_official_template():
    template = (
        ROOT
        / "agentbench"
        / "onboarding"
        / "build_agent_env"
        / "build_dockerfile"
        / "assets"
        / "dockerignore"
    )
    assert template.is_file()
    assert (UNIT / ".dockerignore").read_bytes() == template.read_bytes()


def test_source_manifest_pins_the_reviewed_revision():
    data = json.loads((UNIT / "source-manifest.json").read_text())
    assert data["schema_version"] == "abb.agent-source.v1"
    assert data["repository"] == REPOSITORY
    assert data["revision"] == REVISION


# ------------------------------------------------------------------------ registry


def test_registry_entry_points_at_this_unit():
    registry = load_registry(ROOT / "resources" / "registry.toml")
    entry = registry.find("beacon-math-agent", enabled_only=False)
    assert entry.path == UNIT
    assert entry.framework == "langgraph"


def test_registry_agent_id_matches_the_unit_manifest():
    manifest = _manifest()
    assert manifest["agent_id"] == "beacon-math-agent"
    assert manifest["framework"] == "langgraph"


# ------------------------------------------------------------------------ agent.toml


def test_source_pins_the_reviewed_revision():
    source = _manifest()["source"]
    assert source["method"] == "git"
    assert source["repository"] == REPOSITORY
    assert source["revision"] == REVISION


def test_binding_is_the_outer_entrypoint_with_a_message_key():
    adapter = _manifest()["adapter"]
    assert adapter["type"] == "langgraph"
    assert adapter["binding"] == "bridge.py:create_graph"
    assert adapter["input_key"] == "message"
    assert adapter["output_key"] == "answer"


def test_runtime_env_keys_expose_only_upstream_variables():
    keys = _manifest()["runtime"]["env_keys"]
    assert set(keys) == {
        "MATH_AGENT_DEFAULT_MODEL",
        "MATH_AGENT_CODER_MODEL",
        "MATH_AGENT_STRONG_MODEL",
        "MATH_AGENT_FIGURE_MODEL",
        "MATH_AGENT_LLM_ATTEMPT_TIMEOUT",
        "MATH_AGENT_LLM_TOTAL_TIMEOUT",
        "MATH_AGENT_MAX_MODEL_ITERATIONS",
        "MATH_AGENT_MAX_WRITER_ITERATIONS",
        "MATH_AGENT_MAX_CODE_VERIFY_ITERATIONS",
        "MATH_AGENT_CODE_TIMEOUT",
        "MATH_AGENT_CODE_MEMORY_LIMIT_MB",
    }


def test_dockerfile_widens_the_llm_deadlines_upstream_exposes():
    dockerfile = (UNIT / "Dockerfile").read_text()
    assert "MATH_AGENT_LLM_ATTEMPT_TIMEOUT=360" in dockerfile
    assert "MATH_AGENT_LLM_TOTAL_TIMEOUT=540" in dockerfile


def test_model_route_is_the_single_openai_chat_completions_path():
    route = _manifest()["llm_interception"]["routes"][0]
    assert route["host_patterns"] == ["api.openai.com"]
    assert route["path_patterns"] == ["/v1/chat/completions"]
    assert route["protocol_plugin"] == "openai-chat"
    assert route["credential"] == "openai"


def test_tool_route_covers_only_the_scholar_search_endpoint():
    route = _manifest()["llm_interception"]["tool_routes"][0]
    assert route["host_patterns"] == ["api.semanticscholar.org"]
    assert route["path_patterns"] == ["/graph/v1/paper/search"]
    assert route["methods"] == ["GET"]


def test_replay_is_disabled():
    assert _manifest()["evaluation"]["replay_safe"] is False


# ------------------------------------------------------------------------ binding


def test_binding_accepts_text_and_the_documented_mapping():
    module = _binding()
    assert module._case_problem("Solve the SIR model.") == "Solve the SIR model."
    assert module._case_problem({"message": "Solve it"}) == "Solve it"


def test_binding_rejects_malformed_inputs():
    module = _binding()
    with pytest.raises(ValueError):
        module._case_problem("")
    with pytest.raises(ValueError):
        module._case_problem("   ")
    with pytest.raises(ValueError):
        module._case_problem({"message": "x", "extra": "y"})
    with pytest.raises(ValueError):
        module._case_problem({"prompt": "x"})
    with pytest.raises(ValueError):
        module._case_problem(None)


def test_binding_reports_a_missing_source_checkout():
    module = _binding()
    original = module.SOURCE_SRC
    try:
        module.SOURCE_SRC = Path("/nonexistent/beacon/src")
        agent = module.create_graph()
        with pytest.raises(RuntimeError, match="missing"):
            agent._compiled()
    finally:
        module.SOURCE_SRC = original


def test_binding_reports_a_missing_model_credential_before_building():
    module = _binding()
    agent = module.create_graph()
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            agent.invoke({"message": "problem text"})
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved


@needs_snapshot
def test_initial_state_carries_the_documented_fields():
    module = _binding()
    from pathlib import Path as _Path
    from tempfile import mkdtemp

    out = _Path(mkdtemp(prefix="beacon-contract-"))
    try:
        module._prepend_source_root()
        state = module._initial_state("the problem text", out)
        assert state["problem"] == "the problem text"
        assert state["background"] == ""
        assert state["questions"] == []
        assert state["stage_target"] == "basic"
        assert state["iteration"] == 0
        assert state["output_dir"] == str(out)
        assert state["latex_template"] == "default"
        decision = state["human_decision"]
        assert decision.approved is True
        assert decision.notes == module.REVIEW_NOTE
    finally:
        import shutil

        shutil.rmtree(out, ignore_errors=True)


@needs_snapshot
@needs_langgraph
def test_upstream_graph_compiles_as_published():
    module = _binding()
    module._prepend_source_root()
    try:
        from math_agent.graph import build_graph
    except ModuleNotFoundError as exc:
        # The graph module imports the full upstream runtime (sqlite_vec, psutil, PIL, ...),
        # which only the built image installs; langgraph alone is not enough.
        pytest.skip(f"upstream runtime dependency {exc.name!r} is not installed in this environment")

    graph = build_graph(checkpointer=None, interrupt_before=[])
    nodes = sorted(n for n in graph.get_graph().nodes if not n.startswith("__"))
    assert len(nodes) == 26
    assert "human_review" in nodes


@needs_snapshot
@needs_langgraph
def test_input_field_is_consumed_by_the_analyst_node():
    """The input contract is real: problem is read, not merely declared."""
    module = _binding()
    module._prepend_source_root()
    from math_agent.state import MathModelingState

    fields = MathModelingState.model_fields
    assert "problem" in fields
    source = (SNAPSHOT / "src" / "math_agent" / "nodes" / "analyst.py").read_text()
    assert "state.problem" in source


@needs_snapshot
def test_human_review_passes_through_a_preexisting_decision():
    """The binding's auto-approval is the state path, not the recover-path env var."""
    module = _binding()
    module._prepend_source_root()
    from math_agent.nodes.human_review import human_review_node
    from math_agent.state import HumanDecision, MathModelingState

    approved = MathModelingState(
        human_decision=HumanDecision(approved=True, notes="x"),
    )
    assert human_review_node(approved) == {}

    # Without a decision and without the recover-path env var, the node reports an
    # error rather than inventing an approval.
    saved = os.environ.pop("MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW", None)
    try:
        pending = MathModelingState()
        result = human_review_node(pending)
        assert "errors" in result
    finally:
        if saved is not None:
            os.environ["MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW"] = saved


@needs_snapshot
def test_review_approval_does_not_depend_on_the_recover_env_var():
    """The binding never sets MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW.

    The variable name may appear in the module docstring, which documents why the
    state path is used instead; code must not touch it.
    """
    module = _binding()
    text = (UNIT / "bindings" / "bridge.py").read_text()
    body = text.split('"""', 2)[2] if text.startswith('"""') else text
    assert "MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW" not in body
    assert "AUTO_APPROVE" not in body


# ------------------------------------------------------------------------ Dockerfile


def test_dockerfile_installs_upstream_dependencies_and_the_worker():
    dockerfile = (UNIT / "Dockerfile").read_text()
    for fragment in (
        "FROM python:3.11-slim",
        "langgraph",
        "litellm==1.91.0",
        "opentelemetry-sdk",
        "COPY --chown=agent:agent agent/ ./agent/",
        "COPY bindings/ ./bindings/",
        "COPY agent.toml ./agent.toml",
        "USER agent",
    ):
        assert fragment in dockerfile, fragment


def test_dockerfile_build_gate_compiles_the_documented_graph():
    dockerfile = (UNIT / "Dockerfile").read_text()
    assert "from math_agent.graph import build_graph" in dockerfile
    assert "len(nodes) == 26" in dockerfile


def test_dockerfile_sets_the_litellm_endpoint_upstream_resolves():
    dockerfile = (UNIT / "Dockerfile").read_text()
    assert "OPENAI_API_BASE=https://api.openai.com/v1" in dockerfile
    assert "MATH_AGENT_DEFAULT_MODEL=openai/" in dockerfile


def test_dockerfile_does_not_flip_the_recover_path_env_var():
    dockerfile = (UNIT / "Dockerfile").read_text()
    assert "MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW" not in dockerfile

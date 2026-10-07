"""Issue #226: kulkarnirohit123/cra-agent onboarding contract.

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
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "51-cra-agent"
SNAPSHOT = UNIT / "agent"
REPOSITORY = "https://github.com/kulkarnirohit123/cra-agent"
REVISION = "4d819a56d825ca14013997958eeb3d0e13ab7ebb"

# A source file the secrets scanner is expected to report on. The token shape is what
# gitleaks matches; the value is inert.
SOURCE_WITH_SECRET = (
    'GITHUB_TOKEN = "ghp_9f4b2c7e1a8d3f6b5e2c9a4d7f1b8e3c5a2d6f9"\n'
    "def charge(amount):\n"
    "    return post(amount, headers={'Authorization': 'Bearer ' + GITHUB_TOKEN})\n"
)

# Reading the checkout needs it on disk; a fresh clone does not have it.
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "src" / "agents" / "orchestrator.py").is_file(),
    reason="agent/ is materialized from [source] at prepare time and is not tracked",
)

# Importing the upstream orchestrator pulls in structlog (via src.utils.logger) and
# GitPython (via src.integrations.git_client; the import name is ``git``). Neither is an
# ABB dependency, so a checkout that has not been built cannot exercise these contracts.
# They are skipped with a reason rather than stubbed: a stubbed orchestrator would not be
# the graph.
_MISSING = next(
    (name for name in ("structlog", "git") if importlib.util.find_spec(name) is None),
    None,
)
needs_upstream_deps = pytest.mark.skipif(
    _MISSING is not None,
    reason=f"upstream runtime dependency '{_MISSING}' is not installed in this environment",
)


def _binding():
    spec = importlib.util.spec_from_file_location(
        "issue226_cra_binding", UNIT / "bindings" / "bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest():
    return tomllib.loads((UNIT / "agent.toml").read_text())


def _on_snapshot_path():
    """Put the restored checkout on sys.path the way the binding does."""
    root = str(SNAPSHOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _scratch_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, capture_output=True, check=True)
    return root


def _orchestrator(module):
    """Build the binding's orchestrator class against a scratch repo.

    Returns ``(instance, tmpdir)``; the caller owns the tmpdir.
    """
    _on_snapshot_path()
    from src.integrations.git_client import GitClient
    from src.integrations.jira_client import JiraClient
    from src.integrations.llm_client import LLMClient
    from src.scanners.suppression_store import SuppressionStore

    tmp = TemporaryDirectory(prefix="cra-contract-")
    root = _scratch_repo(tmp.name)
    instance = module._orchestrator_class()(
        repo_path=root,
        llm_client=LLMClient(
            provider="openai", model="gpt-4o", api_key="sk-contract-placeholder",
            base_url="https://api.openai.com/v1",
        ),
        jira_client=JiraClient(base_url="", email="", api_token=""),
        git_client=GitClient(repo_path=root),
        suppression_store=SuppressionStore(db_path=Path(tmp.name) / "s.db"),
    )
    return instance, tmp


# ------------------------------------------------------------------- tracked unit


def test_tracked_unit_is_ascii_only():
    """The unit is published as ASCII source.

    The upstream checkout keeps its own encoding, but nothing this unit adds may depend
    on a non-ASCII environment. The excluded ``agent/`` tree is the restored upstream
    source, not part of this unit's tracked contribution.
    """
    offenders = []
    for path in sorted(UNIT.rglob("*")):
        if not path.is_file() or SNAPSHOT in path.parents:
            continue
        for number, line in enumerate(path.read_bytes().splitlines(), 1):
            if any(byte > 0x7F for byte in line):
                offenders.append(f"{path.relative_to(UNIT)}:{number}")

    assert offenders == [], "non-ASCII tracked content: " + ", ".join(offenders)


# --------------------------------------------------------------------------- input


def test_case_input_is_accepted_as_text_or_message_mapping():
    graph = _binding().create_graph()
    assert graph._source_text(SOURCE_WITH_SECRET) == SOURCE_WITH_SECRET
    assert graph._source_text({"message": SOURCE_WITH_SECRET}) == SOURCE_WITH_SECRET


@pytest.mark.parametrize(
    "value,match",
    [
        ("", "non-empty"),
        ("   \n ", "non-empty"),
        (None, "non-empty"),
        (5, "non-empty"),
        ([], "non-empty"),
        ({}, "exactly"),
        ({"message": "code", "path": "src/app.py"}, "exactly"),
        ({"messages": ["synthetic history"]}, "exactly"),
        ({"message": ""}, "non-empty"),
    ],
)
def test_unsupported_input_is_rejected_before_native_execution(value, match):
    graph = _binding().create_graph()
    with pytest.raises(ValueError, match=match):
        graph._source_text(value)


# -------------------------------------------------------------------------- report


def test_report_states_that_nothing_survived_rather_than_reporting_clean():
    """An empty result must not read as a verdict on the code.

    The upstream scanners swallow their own failures, so "no findings" here can mean
    "the scanner did not run" as easily as "the scanner found nothing". The renderer
    reports the counting facts and claims nothing about the absence of problems.
    """
    text = _binding()._render_report(
        {"raw_findings": [], "filtered_findings": [], "triaged_findings": [],
         "jira_tickets": [], "actions": []}
    )

    assert "No findings survived scanning and filtering" in text
    assert "Files scanned: 1" in text
    for word in ("clean", "safe", "secure", "no vulnerabilities", "no issues"):
        assert word not in text.lower()


def test_report_carries_scanner_evidence_and_triage_for_each_finding():
    state = {
        "raw_findings": [{}, {}],
        "filtered_findings": [{}, {}],
        "triaged_findings": [
            {
                "scanner": "secrets",
                "vuln_id": "github-pat",
                "title": "Hardcoded secret: GitHub Personal Access Token",
                "file_path": "submission.py",
                "line_start": 1,
                "line_end": 1,
                "severity": "critical",
                "triage": {
                    "severity": "critical",
                    "exploitability": "likely",
                    "cra_relevance": ["annex_i_section_1"],
                    "recommended_action": "fix_now",
                    "reasoning": "hardcoded credential in source",
                    "fix_suggestion": "read it from the environment",
                    "confidence": 0.9,
                },
            }
        ],
        "jira_tickets": [],
        "actions": [],
    }
    text = _binding()._render_report(state)

    assert "Raw findings: 2" in text
    assert "Triaged findings: 1" in text
    assert "github-pat" in text
    assert "submission.py:1-1" in text
    assert "recommended_action: fix_now" in text
    assert "read it from the environment" in text


def test_report_shows_a_failed_fix_as_failed():
    """The upstream fixer cannot succeed; the report must not round that up.

    ``FixerAgent._generate_fix`` reads ``file_extension`` off a ``TriagedFinding``,
    which does not define it, so every attempt is caught into ``Action(success=False)``.
    """
    state = {
        "raw_findings": [{}],
        "filtered_findings": [{}],
        "triaged_findings": [{"scanner": "secrets", "triage": {"severity": "critical"}}],
        "jira_tickets": [],
        "actions": [
            {
                "action_type": "fix",
                "description": "Failed to fix abc123",
                "success": False,
                "error": "no fix generated",
                "details": {},
            }
        ],
    }
    text = _binding()._render_report(state)

    assert "failed" in text
    assert "no fix generated" in text


# ------------------------------------------------------ the repaired graph contract


@needs_snapshot
@needs_upstream_deps
def test_upstream_orchestrator_cannot_compile_as_published():
    """Records the defect the binding works around, so a silent upstream fix is visible.

    ``_build_graph`` anchors conditional edges on ``should_triage`` and ``should_fix``
    without ever registering them.
    """
    _on_snapshot_path()
    from src.agents.orchestrator import CRAOrchestrator

    with TemporaryDirectory(prefix="cra-upstream-") as tmp:
        root = _scratch_repo(tmp)
        with pytest.raises(ValueError, match="unknown node"):
            CRAOrchestrator(
                repo_path=root,
                llm_client=object(),
                jira_client=object(),
                git_client=object(),
                suppression_store=object(),
            )


@needs_snapshot
@needs_upstream_deps
def test_repaired_graph_is_the_state_machine_the_docstring_describes():
    instance, tmp = _orchestrator(_binding())
    try:
        graph = instance.graph.get_graph()

        assert set(graph.nodes) == {
            "__start__", "__end__", "scan_commit", "filter_suppressed",
            "triage_findings", "create_jira_tickets", "auto_fix",
        }
        # The two decisions stay conditional; every other hop is unconditional.
        assert {(e.source, e.target) for e in graph.edges if e.conditional} == {
            ("filter_suppressed", "triage_findings"),
            ("filter_suppressed", "__end__"),
            ("create_jira_tickets", "auto_fix"),
            ("create_jira_tickets", "__end__"),
        }
        assert {(e.source, e.target) for e in graph.edges if not e.conditional} == {
            ("__start__", "scan_commit"),
            ("scan_commit", "filter_suppressed"),
            ("triage_findings", "create_jira_tickets"),
            ("auto_fix", "__end__"),
        }
    finally:
        tmp.cleanup()


@needs_snapshot
def test_repair_touches_no_upstream_module():
    """The subclass exists so the restored checkout stays byte-identical."""
    _on_snapshot_path()
    from src.core.models import Finding

    # file_extension belongs to FileChange, which is why the upstream fixer fails.
    assert not hasattr(Finding, "file_extension")
    finding = Finding(
        id="0" * 16, scanner="secrets", title="t", description="d", severity="low",
        file_path="f.py", commit_hash="0" * 40,
    )
    assert not hasattr(finding, "file_extension")


# --------------------------------------------------------------- workspace contract


@needs_snapshot
@needs_upstream_deps
def test_workspace_is_a_git_repository_with_a_local_identity():
    """The fixer branches and commits, so the workspace needs a repo and an identity."""
    module = _binding()
    with TemporaryDirectory(prefix="cra-ws-") as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        commit_info, changed_files = module._materialize_workspace(root, SOURCE_WITH_SECRET)

        assert (root / "submission.py").read_text() == SOURCE_WITH_SECRET
        assert (root / ".git").is_dir()
        assert subprocess.run(
            ["git", "config", "user.email"], cwd=root, capture_output=True, text=True
        ).stdout.strip()
        assert commit_info["hash"] == subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
        ).stdout.strip()
        assert changed_files == [
            {
                "file_path": "submission.py",
                "change_type": "added",
                "old_path": None,
                "hunks": [],
                "file_content": None,
                "file_extension": ".py",
                "language": "python",
            }
        ]


def test_missing_intercepted_credential_fails_before_any_model_call(monkeypatch):
    module = _binding()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        module._build_llm_client()


# --------------------------------------------------------- onboarding declarations


def test_unit_source_and_registry_are_pinned_to_issue226_revision():
    manifest = _manifest()
    source = json.loads((UNIT / "source-manifest.json").read_text())
    registration = load_registry(ROOT / "resources" / "registry.toml").find(
        "cra-agent", enabled_only=False
    )

    assert manifest["source"]["repository"] == REPOSITORY
    assert manifest["source"]["revision"] == REVISION
    assert source["revision"] == manifest["source"]["revision"]
    assert source["repository"] == manifest["source"]["repository"]
    assert registration.path == UNIT
    assert registration.status == "adapting"
    # A newly onboarded integration is registered but not selected for `run`.
    assert registration.enabled is False


def test_binding_declares_the_intercepted_route_and_no_tool_egress():
    manifest = _manifest()
    adapter = manifest["adapter"]
    interception = manifest["llm_interception"]

    assert adapter["type"] == "langgraph"
    assert adapter["binding"] == "bridge.py:create_graph"
    assert adapter["output_key"] == "answer"
    assert interception["credentials"][0]["agent_env"] == "OPENAI_API_KEY"
    assert len(interception["routes"]) == 1
    route = interception["routes"][0]
    assert route["host_patterns"] == ["api.openai.com"]
    assert route["path_patterns"] == ["/v1/chat/completions"]
    # Jira, GitHub and the advisory databases are withheld on purpose and upstream
    # already degrades on each, so no tool route is declared for any of them.
    assert not interception.get("tool_routes")


def test_unit_ships_every_tracked_file_the_build_reads():
    for name in ("README.md", "requirement.md", "Dockerfile", ".dockerignore",
                 "agent.toml", "source-manifest.json", "bindings/bridge.py",
                 "runtime/semgrep_shim.py"):
        assert (UNIT / name).is_file(), name
    assert (UNIT / "ground_truth").is_dir()
    # The upstream checkout is restored, never committed.
    assert "/resources/agents/*/agent/" in (ROOT / ".gitignore").read_text()


@needs_snapshot
def test_restored_checkout_is_faithful_and_safe_to_publish():
    manifest = _manifest()

    assert manifest["source"]["revision"] == REVISION
    assert (SNAPSHOT / "src" / "agents" / "orchestrator.py").is_file()
    assert (SNAPSHOT / "src" / "scanners" / "secrets_scanner.py").is_file()
    assert (SNAPSHOT / "pyproject.toml").is_file()

    # The scan-to-triage path is what this deployment exercises; the daemons are not.
    prompt = (SNAPSHOT / "src" / "agents" / "triage_agent.py").read_text()
    assert "code_snippet" in prompt, "triage must still see the reviewed code"

    assert not any(path.name == ".env" for path in UNIT.rglob("*"))
    assert not any(path.name == ".git" for path in UNIT.rglob("*"))
    assert not any(path.is_symlink() for path in UNIT.rglob("*"))
    assert not (UNIT / "evaluation" / "input-contract.json").exists()


def test_requirement_profile_passes_the_official_kuma_parse():
    """KUMA's own parser reads requirement.md; a substring check of our own text would
    pass no matter what the profile meant."""
    from agentbench.sdk.plugin.kuma.onboarding import validate
    from kuma.repository.agent_profiles import parse_agent_profile

    validate(UNIT)

    profile = parse_agent_profile(UNIT / "requirement.md")
    assert profile.input_type == "text"
    assert (profile.strategy_group.id, profile.strategy_group.version) == (
        "basic-safety-general",
        "1",
    )
    assert set(profile.sections) >= {
        "production_scenario",
        "behaviors_to_test",
        "prohibited_behaviors",
    }
    assert 0 < len(profile.agent_description) <= 2000

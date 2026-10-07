"""ABB boundary for kulkarnirohit123/cra-agent (CRA compliance monitoring Agent).

Native entrypoint
-----------------
``src/main.py`` is a long-running service, not a request handler: ``CRAAgent``
starts a git polling loop and a FastAPI webhook server side by side, and
``GitHubPollingAgent`` polls the GitHub API. Neither exposes a single
request/response call, which is why the upstream README documents only
``python -m src.main`` and ``uvicorn src.webhook.server:app``.

The application logic behind both daemons is
:class:`src.agents.orchestrator.CRAOrchestrator`, a LangGraph state machine over
``AgentState``:

``scan_commit`` -> ``filter_suppressed`` -> (findings?) -> ``triage_findings``
-> ``create_jira_tickets`` -> (fixable?) -> ``auto_fix`` -> END

Its public method is ``CRAOrchestrator.run(commit_info, changed_files)``, which
``CRAAgent.process_commit`` calls once per detected commit with the output of
``DiffAnalyzer.analyze_commit``. This binding invokes that same method: it
materializes the Case input as the one file of a commit inside a private
workspace, builds the same ``[FileChange]`` list ``process_commit`` builds, and
returns the resulting state. Reasoning, prompts, scanners and the graph are
upstream code; no upstream file is modified.

Input mapping
-------------
One Case input is text: the source code to review. The binding writes it to
``submission.py`` in a private git workspace and treats it as a single added
file, which is the smallest faithful stand-in for the commit a daemon would
otherwise hand to ``process_commit``. The extension is ``.py`` because the
upstream scanner set is Python-oriented (``ScannerAgent`` defaults to the
dependency/SAST/secrets trio and ``SASTScanner`` dispatches on file extension).
A ``.py`` name is what lets the SAST ruleset see the file at all; the secrets
scanner is extension-independent.

Adaptations required by this deployment
---------------------------------------
1. **The graph cannot be compiled as published, so two edges are re-anchored.**
   ``CRAOrchestrator._build_graph`` calls
   ``add_edge("filter_suppressed", "should_triage")`` and
   ``add_edge("create_jira_tickets", "should_fix")``, then anchors the two
   conditional edges on those same strings -- but ``should_triage`` and
   ``should_fix`` are never registered with ``add_node``. They are not nodes;
   they exist only in the docstring's ASCII diagram, where they mark where a
   decision is taken. ``StateGraph.compile()`` therefore refuses to build the
   graph:

   ``ValueError: Found edge starting at unknown node 'should_fix'``

   The binding subclasses the orchestrator and re-registers exactly those two
   decisions in their supported form --
   ``add_conditional_edges("filter_suppressed", self._should_triage_condition,
   {...})`` and ``add_conditional_edges("create_jira_tickets",
   self._should_fix_condition, {...})``. The resulting graph is the state
   machine the upstream docstring describes, edge for edge: the unconditional
   hop to a decision marker and the decision taken at that marker collapse
   into one conditional edge. Node bodies, the two condition functions, the
   four agents and every prompt remain upstream code, and no upstream file is
   modified. The defect is reported in this unit's README.

2. **Daemon lifecycle replaced by one call.** ``CRAAgent.__init__`` builds a
   ``GitMonitor``, a ``GitHubPoller`` and signal handlers for a process that
   never returns. The binding constructs the orchestrator directly with the same
   four collaborators ``CRAAgent`` passes (LLM client, Jira client, git client,
   suppression store) and calls ``run`` once per input. ``src/main.py``,
   ``src/webhook/``, ``src/core/git_monitor.py`` and
   ``src/core/github_poller.py`` are therefore not exercised.

3. **Jira and GitHub are absent, and upstream already handles that.**
   ``JiraAgent.create_ticket`` catches its own client failures and returns a
   ``JiraTicket(key="FAILED", status="Error")``; ``GitClient.push`` catches and
   returns ``False``, and ``GitClient.create_pull_request`` is upstream's own
   placeholder that returns a constructed URL without contacting a forge.
   ``FixerAgent.fix_finding`` wraps the whole fix attempt and returns
   ``Action(success=False, error=...)`` on failure. The binding supplies no
   ticket server and no remote, so those documented degradation paths run
   exactly as written rather than being stubbed into false success.

4. **Execution configuration.** ``CRAOrchestrator.run`` takes no ``config``
   parameter, so the invocation config ABB passes cannot be forwarded as an
   argument. The binding applies it with LangChain's
   ``set_config_context`` around the call, which is the mechanism the ABB
   binding handbook describes for native lifecycles that lack a config
   parameter. The context object is used unchanged and never serialized.

5. **Model client.** ``CRAOrchestrator`` receives ``LLMClient``, whose
   ``_get_openai_client`` builds a ``ChatOpenAI`` pointing at
   ``base_url``. The binding supplies the OpenAI-protocol endpoint declared in
   ``agent.toml``'s ``[[llm_interception.routes]]``, so the two call sites that
   reach a model -- ``TriageAgent.triage_finding`` and
   ``FixerAgent._generate_fix``, both through ``LLMClient.generate_json`` --
   are observed by ABB's interceptor. Model interception replaces the request
   with the configured run model, so behavior follows the benchmark's model.

6. **A real workspace, because four upstream components need one.**
   ``ScannerAgent`` resolves file paths under ``repo_path``,
   ``SuppressionStore`` opens a SQLite ledger, ``GitClient`` calls
   ``Repo(path)`` and ``FixerAgent`` branches and commits. The binding creates a
   throwaway git repository per input, with ``user.name``/``user.email`` set in
   that repository's own config so the fixer's ``commit`` can succeed without a
   global git identity. It is deleted after the call.

Input example: the text of one Python source file.
Output shape: ``{"answer": "<rendered scan and triage report>"}``. The report is
built only from the returned state; a run that finds nothing says so, and a
native failure propagates as an exception rather than being rendered as a
successful-looking answer.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

# ``resources/agents/51-cra-agent/agent/`` is the upstream repository root.
SOURCE_ROOT = Path(__file__).resolve().parent.parent / "agent"

# The host whose OpenAI-protocol endpoint agent.toml declares to the interceptor.
# Model interception rewrites the request to the configured run model, so under
# ABB this is always the declared host. The environment override exists only so
# the binding can be smoke-tested outside ABB, where no interceptor is running.
INTERCEPTED_BASE_URL = os.environ.get("ABB_OPENAI_BASE_URL", "https://api.openai.com/v1")

# Deployment defaults. Kept in the binding so no upstream file is edited.
CHAT_MODEL_NAME = os.environ.get("ABB_CHAT_MODEL_NAME", "gpt-4o")
SUBMISSION_FILENAME = "submission.py"

# Placeholder commit metadata. A daemon would take this from the polled commit;
# one Case input carries no commit, so the hash is derived from the input text to
# stay deterministic and to keep finding ids stable across runs.
COMMIT_AUTHOR = "ABB Case Input"
COMMIT_MESSAGE = "Case input"


def _prepend_source_root() -> None:
    """Make the upstream top-level packages (config, src) importable.

    Upstream imports are rooted at the repository -- ``from config.settings
    import ...``, ``from src.agents.orchestrator import ...`` -- so the checkout
    directory itself has to be on the path.
    """
    root = str(SOURCE_ROOT)
    if not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"Upstream source directory is missing: {SOURCE_ROOT}")
    if root not in sys.path:
        sys.path.insert(0, root)


def _git(args: list[str], cwd: Path) -> None:
    """Run one git command in the private workspace.

    Raises:
        RuntimeError: git is missing or the command failed. The workspace is
            private and disposable, so a failure here is a deployment fault
            rather than a condition to work around.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()[:400]}")


def _materialize_workspace(root: Path, source_text: str) -> tuple[dict, list[dict]]:
    """Write the input as one committed file and return the orchestrator's inputs.

    ``CRAAgent.process_commit`` hands ``CRAOrchestrator.run`` a commit dict and
    the ``FileChange`` list built from ``DiffAnalyzer.analyze_commit``. This
    rebuilds the same pair for a single added file.

    ``git`` is initialized, committed and given a local identity because
    ``FixerAgent`` calls ``GitClient.create_branch`` (which checks out the base
    branch) and ``GitClient.commit`` on this directory.

    Returns:
        ``(commit_info, changed_files)`` -- plain dicts, matching what
        ``process_commit`` passes upstream.
    """
    submission = root / SUBMISSION_FILENAME
    submission.write_text(source_text, encoding="utf-8")

    _git(["init", "-b", "main"], root)
    _git(["config", "user.email", "cra-agent@abb.invalid"], root)
    _git(["config", "user.name", "CRA-AGENT"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", COMMIT_MESSAGE], root)
    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()

    commit_info = {
        "hash": commit_hash,
        "short_hash": commit_hash[:7],
        "author": COMMIT_AUTHOR,
        "author_email": "case-input@abb.invalid",
        "message": COMMIT_MESSAGE,
        "timestamp": "1970-01-01T00:00:00",
        "branch": "main",
        "parent_hash": None,
    }
    changed_files = [
        {
            "file_path": SUBMISSION_FILENAME,
            "change_type": "added",
            "old_path": None,
            "hunks": [],
            "file_content": None,
            "file_extension": ".py",
            "language": "python",
        }
    ]
    return commit_info, changed_files


def _build_llm_client():
    """Build the upstream LLM client against the intercepted endpoint.

    ``LLMClient`` reads its ``base_url`` from its own constructor, so the
    binding -- not ``config.settings`` -- decides where model traffic goes.
    ``OPENAI_API_KEY`` is supplied by ABB's credential interception.

    The credential is checked before the upstream import so that a missing
    credential fails as a credential error even where the upstream checkout is
    not importable.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be supplied by model interception")

    from src.integrations.llm_client import LLMClient

    return LLMClient(
        provider="openai",
        model=CHAT_MODEL_NAME,
        api_key=api_key,
        base_url=INTERCEPTED_BASE_URL,
        temperature=0.1,
        max_tokens=4096,
    )


@lru_cache(maxsize=1)
def _orchestrator_class():
    """Return ``CRAOrchestrator`` with its two mis-anchored edges re-registered.

    ``CRAOrchestrator._build_graph`` anchors two conditional edges on the
    strings ``should_triage`` and ``should_fix`` without ever registering them,
    so ``compile()`` raises ``ValueError: Found edge starting at unknown node``.
    Those two names are decision markers from the upstream docstring's diagram,
    not nodes.

    This subclass restates the same graph with each marker folded into the
    conditional edge of the node that precedes it. Every node body, both
    condition functions and every agent class are the upstream ones; only the
    two edge registrations differ. No upstream file is modified -- the subclass
    exists so the published revision under ``agent/`` stays byte-identical.

    Imported lazily because ``agent/`` only reaches ``sys.path`` after
    :func:`_prepend_source_root` has run.
    """
    from langgraph.graph import END, StateGraph

    from src.agents.orchestrator import CRAOrchestrator
    from src.core.models import AgentState

    class CRAOrchestratorWithRepairedGraph(CRAOrchestrator):
        """CRAOrchestrator whose compiled graph matches its documented states."""

        def _build_graph(self):
            workflow = StateGraph(AgentState)

            workflow.add_node("scan_commit", self._scan_commit_node)
            workflow.add_node("filter_suppressed", self._filter_suppressed_node)
            workflow.add_node("triage_findings", self._triage_findings_node)
            workflow.add_node("create_jira_tickets", self._create_jira_tickets_node)
            workflow.add_node("auto_fix", self._auto_fix_node)

            workflow.set_entry_point("scan_commit")
            workflow.add_edge("scan_commit", "filter_suppressed")

            # Upstream: add_edge("filter_suppressed", "should_triage") followed by
            # add_conditional_edges("should_triage", ...). Collapsed here.
            workflow.add_conditional_edges(
                "filter_suppressed",
                self._should_triage_condition,
                {"triage": "triage_findings", "end": END},
            )

            workflow.add_edge("triage_findings", "create_jira_tickets")

            # Upstream: add_edge("create_jira_tickets", "should_fix") followed by
            # add_conditional_edges("should_fix", ...). Collapsed here.
            workflow.add_conditional_edges(
                "create_jira_tickets",
                self._should_fix_condition,
                {"fix": "auto_fix", "end": END},
            )

            workflow.add_edge("auto_fix", END)

            return workflow.compile()

    return CRAOrchestratorWithRepairedGraph


def _render_report(state: Mapping) -> str:
    """Render the returned ``AgentState`` as the report text the Case receives.

    Only values present in the state are printed. An empty finding list is
    reported as no findings; nothing is inferred, summarized from memory or
    filled in when a field is absent.
    """
    triaged = list(state.get("triaged_findings") or [])
    raw = list(state.get("raw_findings") or [])
    filtered = list(state.get("filtered_findings") or [])
    tickets = list(state.get("jira_tickets") or [])
    actions = list(state.get("actions") or [])

    lines: list[str] = [
        "CRA-AGENT scan report",
        "",
        f"Files scanned: 1 ({SUBMISSION_FILENAME})",
        f"Raw findings: {len(raw)}",
        f"After suppression filtering: {len(filtered)}",
        f"Triaged findings: {len(triaged)}",
    ]

    if not triaged:
        lines += [
            "",
            "No findings survived scanning and filtering for this input, so no",
            "triage was performed and no tickets or fixes were produced.",
        ]
        return "\n".join(lines)

    lines += ["", "Triaged findings", ""]
    for index, finding in enumerate(triaged, start=1):
        triage = finding.get("triage") or {}
        lines += [
            f"--- Finding {index} ---",
            f"Scanner: {finding.get('scanner', '')}",
            f"Rule / vulnerability id: {finding.get('vuln_id') or '(none)'}",
            f"Title: {finding.get('title', '')}",
            f"Location: {finding.get('file_path', '')}:"
            f"{finding.get('line_start', 0)}-{finding.get('line_end', 0)}",
            f"Scanner-reported severity: {finding.get('severity', '')}",
            "",
            "Triage assessment:",
            f"  severity: {triage.get('severity', '')}",
            f"  exploitability: {triage.get('exploitability', '')}",
            f"  cra_relevance: {', '.join(triage.get('cra_relevance') or []) or '(none)'}",
            f"  recommended_action: {triage.get('recommended_action', '')}",
            f"  confidence: {triage.get('confidence', '')}",
            f"  reasoning: {triage.get('reasoning', '')}",
            f"  fix_suggestion: {triage.get('fix_suggestion') or '(none provided)'}",
            "",
        ]

    lines += ["Ticket attempts (no ticket server is configured for this deployment):"]
    if tickets:
        for ticket in tickets:
            lines.append(
                f"  {ticket.get('key', '')} [{ticket.get('status', '')}] "
                f"{ticket.get('priority', '')} {ticket.get('title', '')}"
            )
    else:
        lines.append("  none")

    lines += ["", "Fix attempts (no remote is configured for this deployment):"]
    if actions:
        for action in actions:
            outcome = "succeeded" if action.get("success") else "failed"
            detail = action.get("error") or (action.get("details") or {}).get("explanation") or ""
            lines.append(
                f"  {action.get('action_type', '')} {outcome}: "
                f"{action.get('description', '')} {detail}".rstrip()
            )
    else:
        lines.append("  none")

    return "\n".join(lines)


class CRAAgentGraph:
    """Drive the upstream CRA workflow for one ABB Input.

    ``invoke``/``ainvoke`` accept the source text, or a mapping whose single
    ``message`` field carries it, and return ``{"answer": <report>}``. The
    native state is not exposed because ``agent.toml`` sets
    ``output_key = "answer"``.

    Each input runs in its own disposable git workspace, deleted when the call
    returns. ``CRAOrchestrator`` binds a repository path at construction time
    (through ``ScannerAgent``, ``FixerAgent`` and ``DiffAnalyzer``), so a
    workspace cannot be reused across inputs without carrying a fix branch from
    the previous one into the next. The workflow is one-shot by nature: a
    daemon builds a fresh orchestrator per commit.

    The LLM client is built and released per call rather than cached. It wraps
    an ``httpx``-backed ``ChatOpenAI`` whose connection pool belongs to the
    event loop that created it, so a cached client would break on the second
    input if the loader ever ran one on a different loop. Construction is
    cheap -- the upstream client opens its transport lazily.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _source_text(value: object) -> str:
        """Accept the Case text, or a mapping carrying exactly one message field."""
        if isinstance(value, Mapping):
            if set(value) != {"message"}:
                raise ValueError("Supply the Case Input as text, or exactly {'message': text}")
            value = value["message"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Case Input must be non-empty text")
        return value

    async def _execute(self, source_text: str, workspace: Path, config: object) -> dict:
        """Run one scan in ``workspace`` and return the rendered report.

        The orchestrator is built per call, so a fix branch created by one input
        never leaks into the next. ``set_config_context`` is what carries ABB's
        invocation config into ``CRAOrchestrator.run``, whose signature has no
        ``config`` parameter.
        """
        from langchain_core.runnables.config import set_config_context

        # Must precede every ``src.*`` import: upstream packages live under agent/.
        _prepend_source_root()

        from src.integrations.git_client import GitClient
        from src.integrations.jira_client import JiraClient
        from src.scanners.suppression_store import SuppressionStore

        root = workspace / "repo"
        root.mkdir()
        commit_info, changed_files = _materialize_workspace(root, source_text)

        llm_client = _build_llm_client()
        try:
            orchestrator = _orchestrator_class()(
                repo_path=root,
                llm_client=llm_client,
                # No ticket server: JiraAgent turns the client failure into its
                # own FAILED ticket, which is upstream's documented behavior.
                jira_client=JiraClient(base_url="", email="", api_token=""),
                git_client=GitClient(repo_path=root),
                suppression_store=SuppressionStore(db_path=workspace / "suppressions.db"),
            )

            with set_config_context(dict(config or {})):
                state = await orchestrator.run(commit_info, changed_files)
        finally:
            await llm_client.close()

        return {"answer": _render_report(state)}

    async def ainvoke(self, value: object, config: object = None, *, context: object = None) -> dict:
        """Run the native workflow once and return the rendered report.

        Args:
            value: The Case Input as text, or ``{"message": <text>}``.
            config: Process-local LangChain ``RunnableConfig`` from ABB.
            context: Not used. ``agent.toml`` declares no ``[adapter.context]``.
        Returns:
            ``{"answer": <report>}``.
        Raises:
            ValueError: The Case Input is not usable text.
            RuntimeError: The workspace or a git step failed.
        """
        source_text = self._source_text(value)
        with TemporaryDirectory(prefix="abb-cra-") as workspace:
            return await self._execute(source_text, Path(workspace), config)

    def invoke(self, value: object, config: object = None, *, context: object = None) -> dict:
        """Synchronous form of :meth:`ainvoke`, for callers without an event loop."""
        return asyncio.run(self.ainvoke(value, config))

    def close(self) -> None:
        """No persistent resources are held; the workspace is per-call.

        Implemented because the loader calls it on shutdown. It is safe to
        repeat and safe to call after a failed construction.
        """


def create_graph() -> CRAAgentGraph:
    """Return a fresh binding instance for one ABB Case."""
    return CRAAgentGraph()

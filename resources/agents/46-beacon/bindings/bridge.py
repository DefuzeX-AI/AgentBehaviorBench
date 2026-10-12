"""ABB boundary for 123-qw-as/Beacon (Math Modeling Agent).

Native entrypoint
-----------------
The repository publishes one program, ``math-agent`` (``[project.scripts]`` ->
``math_agent.cli:app``), and its ``run`` command is a thin caller around a single
LangGraph factory. The graph itself is built by
``math_agent.graph.build_graph(*, checkpointer=None, interrupt_before=None)`` --
a synchronous zero-argument-callable factory that compiles a 26-node
``StateGraph`` over ``math_agent.state.MathModelingState`` and touches no
credential, no filesystem path and no network at construction time. The
repository's own end-to-end harness calls that factory directly
(``scripts/e2e_plan_d.py:186``, ``scripts/e2e_plan_c.py:184``) with
``build_graph()`` -- no checkpointer, no ``interrupt_before`` -- and then
``g.invoke(<initial state>)``. This binding invokes the same factory and the same
graph; the CLI's checkpointing, ``resume``/``recover`` supervision and Rich
reporting exist to survive a crashed long-running shell session and are not part
of what one Input asks for.

Input mapping
-------------
One Case input is text: a mathematical-modelling problem statement.
``cli.run`` builds the initial state from a problem JSON file as

    "problem":    title + "\\n" + "\\n".join(questions)
    "background": background
    "questions":  questions

A single text input carries no separate title / background / question split, so
the text goes into ``problem`` -- the field ``analyst_node`` reads and passes to
``build_prompt`` (``src/math_agent/nodes/analyst.py:29``), and the field the rest
of the graph consumes through ``problem_blueprint``, ``writer`` and ``latex``.
``background`` and ``questions`` keep their native defaults; splitting the text
into them would be inventing structure the input does not have. This is the
"ordinary natural-language request" case the binding handbook describes, and
``problem`` is confirmed to be read rather than declared: the whole pipeline
consumes it, unlike a state field that no node ever reads.

The rest of the initial state is the public caller's:

* ``stage_target="basic"`` and ``iteration=0`` -- ``cli.run``'s starting stage.
* ``output_dir`` -- a private directory for this Input. ``latex_node`` writes
  ``paper.tex`` / ``paper.md`` there, the coder runs its generated scripts with
  that directory as the working directory (``nodes/coder.py:2750``), and
  ``finalizer_node`` validates and digests the artifacts in it.
* ``human_decision`` -- ``HumanDecision(approved=True, ...)``. ABB has no human
  at the terminal, so the graph would otherwise stop at ``human_review`` and
  ``after_human_review`` would route to END with an unapproved paper. Upstream
  supports exactly this deployment through ``run --no-interrupt``, which sets the
  same approved decision in the initial state
  (``cli.run``: ``HumanDecision(approved=True, notes="--no-interrupt")``) and
  compiles the graph without an interrupt. Setting the decision in the initial
  state -- rather than flipping the ``MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW``
  environment variable that the *recover* path uses -- reproduces the ``run``
  command this binding is standing in for, and keeps the flag from masking a
  genuinely absent decision.
* ``data_dir`` / ``data_files`` -- left at their native defaults (``None`` and
  ``[]``). Upstream accepts attachments through the problem JSON; one text Input
  carries none, and the deployment provides no attachment channel. Nodes that
  would summarize attachments have nothing to summarize.
* ``latex_template="default"`` -- upstream's default article template. The
  ``gmcm`` competition template additionally requires a school, team id and
  member names, which a text Input does not carry.

Output
------
``latex_node`` writes ``paper.md`` (the full paper in Markdown, always written,
before it attempts a PDF) into the run's ``output_dir``, and ``finalizer_node``
then writes ``completion.json`` / ``final_state.json`` and returns a
``FinalizationReport``. ``answer`` is the ``paper.md`` the graph produced, byte
for byte; ``status``, ``warnings`` and ``artifacts`` carry the finalizer's
report so a reader can tell a clean run from a degraded one.

The graph can also end earlier than that: ``after_paper_critic``,
``after_model_critic`` and ``after_model_code_consistency`` all have a ``stop``
edge to END for a run that exhausts its retry budget. In that case no paper
exists, and the binding reports the native terminal state -- which critic
stopped the run, with its score, verdict, issues and the accumulated
``state.errors`` -- rather than fabricating or half-rendering a paper. Nothing
is synthesized in either branch.

Adaptations required by this deployment
---------------------------------------
1. **The upstream project is put on the import path instead of being installed.**
   Upstream is a ``src/`` layout whose ``math_agent/templates`` directory is
   package data with no ``MANIFEST.in``; a non-editable ``pip install .``
   therefore yields a package that cannot find ``paper.tex.j2`` and fails inside
   ``latex_node``. The Dockerfile installs upstream's declared dependency set and
   this binding prepends ``agent/src`` to ``sys.path``, which is what upstream's
   own ``uv sync`` editable install amounts to, and what
   ``[tool.pytest.ini_options] pythonpath = ["src"]`` assumes for the tests.

2. **Long-running model work is serialized through upstream's own transport.**
   ``math_agent.llm`` spawns a LiteLLM worker process with
   ``multiprocessing``'s ``spawn`` context and kills it on deadline
   (``src/math_agent/transport.py``). No model client is constructed here and no
   call is forwarded: the whole model boundary is upstream's.

3. **Academic search is expected to be the one external tool.** The references
   section calls ``tools/scholar.py``, which GETs the Semantic Scholar search
   endpoint; that destination is declared in ``agent.toml``. Upstream already
   degrades to ``src/math_agent/references/builtin_library.json`` on any
   non-200 answer, so a blocked call changes the bibliography, not the run.

4. **No checkpointer and no interrupt.** ``build_graph(checkpointer=None,
   interrupt_before=[])``. The CLI attaches a ``SqliteSaver`` so ``resume`` and
   ``recover`` can continue an interrupted run; ABB drives one Input to
   completion and delivers no continuation, so a checkpoint would only add a
   state file nothing reads. Upstream's own harness compiles the graph the same
   way.

5. **A writable output directory per Input.** ``latex_node``, ``finalizer_node``
   and the coder all require ``state.output_dir`` to exist and be writable. Each
   Input gets its own private directory under the system temporary root, which is
   removed when the call returns -- including after a failure, so repeated runs
   cannot accumulate state.

Diagram generation needs a vision-capable model: ``figure_critic`` and
``figure_analysis`` send rendered figures as image content. ABB's default model
target accepts ``text`` and ``image`` input, so the requests are routed, but
whether they succeed is the run model's capability, not this binding's.

Input example: the text of one mathematical-modelling problem.
Output shape: ``{"answer": "<paper.md>", "status": ..., "warnings": [...],
"artifacts": [...]}``. Native failures propagate as exceptions; a run that ends
without a paper says so explicitly.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

# ``resources/agents/46-beacon/agent/`` is the upstream repository root, and its
# ``src/`` directory holds the ``math_agent`` package. The binding puts that
# directory on the import path rather than relying on an installed distribution,
# because upstream ships templates as package data without a MANIFEST.in.
SOURCE_ROOT = Path(__file__).resolve().parent.parent / "agent"
SOURCE_SRC = SOURCE_ROOT / "src"

# The paper is the deliverable the CLI reports ("done. paper at {out}/paper.md").
PAPER_FILENAME = "paper.md"

# Recorded on the review decision so a run's provenance is legible in the state
# and in final_state.json. Upstream's own --no-interrupt path records its flag
# here; the deployment is named instead because ABB is what is unattended.
REVIEW_NOTE = "unattended ABB deployment"

# Cap on how much of the terminal state is rendered when a run ends before the
# paper stage, so one pathological run cannot turn the answer into a dump.
MAX_ERRORS_REPORTED = 12
MAX_ISSUES_PER_CRITIC = 3


def _prepend_source_root() -> None:
    """Make ``math_agent`` importable from the pinned checkout.

    Upstream's packages are rooted at ``src/``, so that directory -- not the
    repository root -- is what ``sys.path`` needs. Imported lazily rather than at
    module scope so that a missing or half-restored checkout is reported as such
    instead of as an unrelated import error.
    """
    if not (SOURCE_SRC / "math_agent" / "graph.py").is_file():
        raise RuntimeError(f"Upstream source directory is missing: {SOURCE_SRC}")
    root = str(SOURCE_SRC)
    if root not in sys.path:
        sys.path.insert(0, root)


def _require_model_credential() -> None:
    """Fail as a credential error before spending time on graph construction.

    ``OPENAI_API_KEY`` is the environment name ``agent.toml`` declares to the
    interceptor, and it is what litellm reads for every ``openai/...`` model this
    deployment uses. Checked up front so an unconfigured container reports a
    missing credential rather than a model call that failed several nodes later.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must be supplied by model interception")


def _case_problem(value: object) -> str:
    """Accept the Case text, or a mapping carrying exactly one message field.

    ``agent.toml`` sets ``input_key = "message"``, so ABB wraps a scalar Input as
    ``{"message": <text>}``; a mapping Input passes through unchanged. Anything
    else is rejected rather than coerced, because a wrong shape here would be
    silently mapped onto the problem statement.
    """
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply the Case Input as text, or exactly {'message': text}")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case Input must be non-empty text")
    return value


def _initial_state(problem: str, output_dir: Path) -> dict:
    """Build the initial state the public ``run`` command builds for one problem.

    Mirrors ``cli.run`` (problem/background/questions, starting stage, iteration
    and ``output_dir``) plus the approved review decision that ``run
    --no-interrupt`` records, and leaves the attachment fields at their native
    defaults. ``HumanDecision`` is imported here rather than at module scope so
    the source checkout is only required when a run actually starts.
    """
    from math_agent.state import HumanDecision

    return {
        "problem": problem,
        "background": "",
        "questions": [],
        "stage_target": "basic",
        "iteration": 0,
        "output_dir": str(output_dir),
        "data_dir": None,
        "data_files": [],
        "latex_template": "default",
        "human_decision": HumanDecision(approved=True, notes=REVIEW_NOTE),
    }


def _critic_line(report: object) -> str:
    """Render one ``CriticReport`` field by field, without interpretation."""
    target = getattr(report, "target", "") or ""
    critic_type = getattr(report, "critic_type", "") or ""
    stage = getattr(report, "stage", None) or ""
    score = getattr(report, "score", "")
    approved = getattr(report, "approved", None)
    label = f"{target}" + (f"/{critic_type}" if critic_type else "")
    if stage:
        label += f" [{stage}]"
    line = f"  {label}: score={score} approved={approved}"
    issues = list(getattr(report, "issues", []) or [])
    if issues:
        rendered = []
        for issue in issues[:MAX_ISSUES_PER_CRITIC]:
            text = getattr(issue, "problem", None) or str(issue)
            rendered.append(" ".join(str(text).split())[:200])
        line += f"\n    issues ({len(issues)}): " + " | ".join(rendered)
    return line


def _terminal_report(state: object, completion: object) -> str:
    """Describe a run that ended before the paper stage.

    Only values already present in the returned state are printed. The point is
    to say where the graph stopped and on whose verdict, not to summarize the
    modelling work the run never finished.
    """
    errors = list(getattr(state, "errors", []) or [])
    critics = list(getattr(state, "critic_reports", []) or [])
    consistency = list(getattr(state, "model_code_reports", []) or [])
    models = list(getattr(state, "model_versions", []) or [])

    lines = [
        "BEACON run ended before a paper was produced.",
        "",
        "The graph returned without writing paper.md. Upstream routes to END from",
        "after_paper_critic, after_model_critic and after_model_code_consistency",
        "when the retry budget is exhausted, so no paper.tex, paper.md or",
        "completion.json exists for this Input. The native terminal state follows.",
        "",
        f"Model versions produced: {len(models)}"
        + (f" (stages: {', '.join(m.stage for m in models)})" if models else ""),
        f"Critic reports: {len(critics)}",
        f"Model-code consistency reports: {len(consistency)}",
        f"Finalization: {getattr(completion, 'status', None) or '(never reached)'}",
    ]

    if critics:
        lines += ["", "Critic verdicts"]
        lines += [_critic_line(report) for report in critics[-6:]]

    if consistency:
        lines += ["", "Model-code consistency"]
        for report in consistency[-2:]:
            lines.append(
                f"  score={getattr(report, 'score', '')} "
                f"approved={getattr(report, 'approved', '')} "
                f"missing_variables={list(getattr(report, 'missing_variables', []) or [])[:8]}"
            )

    if errors:
        lines += ["", f"Accumulated errors ({len(errors)})"]
        for error in errors[:MAX_ERRORS_REPORTED]:
            lines.append("  " + " ".join(str(error).split())[:300])
        if len(errors) > MAX_ERRORS_REPORTED:
            lines.append(f"  ... and {len(errors) - MAX_ERRORS_REPORTED} more")

    return "\n".join(lines)


def _result(state: object, output_dir: Path) -> dict:
    """Return the paper the graph wrote, or the native state that stopped it.

    ``finalizer_node`` records its ``FinalizationReport`` in the state, so the
    status and warnings come from the run itself. ``artifacts`` lists the files
    the finalizer digested, by name only.
    """
    completion = getattr(state, "finalization", None)
    paper_path = output_dir / PAPER_FILENAME

    if paper_path.is_file() and paper_path.stat().st_size > 0:
        answer = paper_path.read_text(encoding="utf-8")
    else:
        answer = _terminal_report(state, completion)

    artifacts = sorted(getattr(completion, "artifacts", {}) or {})
    return {
        "answer": answer,
        "status": getattr(completion, "status", None) or "no-finalization",
        "warnings": list(getattr(completion, "warnings", []) or []),
        "artifacts": artifacts,
    }


class BeaconAgent:
    """Drive the upstream Beacon graph for one ABB Input.

    ``invoke`` accepts the problem text, or a mapping whose single ``message``
    field carries it, and returns the paper the graph produced.

    The native application is synchronous throughout -- every node is a plain
    function and the model transport blocks on a pipe read
    (``src/math_agent/transport.py``) -- so no ``ainvoke`` is implemented. ABB's
    async adapter runs ``invoke`` in a worker thread, which is the same execution
    the CLI gets from the main thread.

    The compiled graph is created on first use and reused for later Inputs in the
    same Case. It holds no per-Input state: without a checkpointer, every
    ``invoke`` starts from the state the binding passes, and the graph's own
    node functions carry no module-level run state. The CLI targets this factory
    once per run in the same way.

    Each Input runs in its own disposable output directory. ``latex_node`` and
    ``finalizer_node`` write ``paper.tex``, ``paper.md``, ``completion.json`` and
    ``final_state.json`` there, and the coder executes generated scripts with that
    directory as their working directory, so a directory cannot be reused across
    Inputs without carrying the previous problem's artifacts into the next.
    """

    def __init__(self) -> None:
        self._graph = None
        self._closed = False

    def _compiled(self):
        """Compile the native graph once, on first use.

        ``build_graph`` is a pure keyword-argument factory: it constructs no
        client and reads no credential, so compiling it eagerly in ``__init__``
        would only move a failure away from the call that can report it.
        """
        if self._closed:
            raise RuntimeError("Binding is closed")
        if self._graph is None:
            _prepend_source_root()
            from math_agent.graph import build_graph

            # No checkpointer and no interrupt, matching the repository's own
            # harness. The CLI's SqliteSaver exists for resume/recover.
            self._graph = build_graph(checkpointer=None, interrupt_before=[])
        return self._graph

    def invoke(self, value: object, config: object = None, *, context: object = None) -> dict:
        """Run the native pipeline once and return its paper.

        Args:
            value: The Case Input as text, or ``{"message": <text>}``.
            config: Process-local LangChain ``RunnableConfig`` from ABB, passed to
                the compiled graph unchanged. It may carry callbacks, tags and
                ``configurable.thread_id``; the graph accepts all of them and the
                binding neither inspects nor serializes the object.
            context: Not used. ``agent.toml`` declares no ``[adapter.context]``.
        Returns:
            ``{"answer": <paper.md>, "status": ..., "warnings": [...],
            "artifacts": [...]}``.
        Raises:
            ValueError: The Case Input is not usable text.
            RuntimeError: The source checkout or the model credential is missing.
        """
        problem = _case_problem(value)
        _require_model_credential()

        output_dir = Path(tempfile.mkdtemp(prefix="abb-beacon-"))
        try:
            graph = self._compiled()
            state = graph.invoke(_initial_state(problem, output_dir), config=config)
            return _result(state, output_dir)
        finally:
            # Removed on failure as well: the artifacts of an incomplete run are
            # already reported through the terminal state, and keeping them would
            # accumulate one directory per Input.
            shutil.rmtree(output_dir, ignore_errors=True)

    def close(self) -> None:
        """Drop the compiled graph and reject further invocations.

        The graph owns no client, connection or temporary directory: the LiteLLM
        worker that upstream's transport spawns is created and reaped per call,
        and each Input's output directory is removed when that call returns. The
        only resource this instance holds is the compiled graph itself, so
        releasing it is the whole of cleanup. Safe to repeat and safe to call
        before a graph was ever compiled.
        """
        self._closed = True
        self._graph = None


def create_graph() -> BeaconAgent:
    """Return a fresh binding instance for one ABB Case."""
    return BeaconAgent()

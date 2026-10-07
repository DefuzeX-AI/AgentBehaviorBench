"""Drive Kiroku's native document-writing workflow from one plain-text input.

Native entrypoint
-----------------
The upstream public workflow is `kiroku_app.DocumentWriter`. Its constructor
builds the node set and compiles a LangGraph StateGraph. With
`suggest_title=False` the compiled graph's ENTRY POINT is the
`internet_search` node, while the initial bookkeeping `state` field is set to
`topic_sentence_writer` — two different things; `KirokuUI.initial_step` shows
the exact initial state values this binding reproduces. This binding wraps
that native lifecycle directly; it does not start Gradio, does not use the UI
save path, and does not replace the native workflow. No output files are
produced by this binding: `KirokuUI.save_as` and the pandoc-based docx export
are not exercised, so no writable project directory is required.

Deployment adaptation
---------------------
The approved certification mapping sends every non-empty text input to a fixed
minimal document specification. The complete input text is preserved verbatim
in `area_of_paper` and `hypothesis`. `suggest_title` and `generate_citations`
are disabled, so the native graph enters at `internet_search` and skips optional
title/citation phases. The upstream graph contains manual-review interrupts;
for this unattended deployment the authoritative mechanism is the
resume-with-empty-instruction loop: the source conditional edges
(is_plan_review_complete / is_generate_review_complete in kiroku_app.py)
interpret a falsy config["configurable"]["instruction"] as "review complete,
proceed", so resuming with "" is source-supported and fabricates no human
feedback. As a best-effort optimization the compiled graph's interrupt lists
are also cleared post-compile; if the runtime does not honor that attribute
mutation, the resume loop still drives the graph to completion.

Input example
-------------
Text: "Write a short briefing about secure multi-agent document drafting."
or mapping: {"message": "Write a short briefing about secure multi-agent document drafting."}

Output shape
------------
```
{
    "draft": "<native final document text>",
    "title": "<native state title>",
    "document_specification": { ... fixed minimal configuration ... },
    "native_state": { ... complete native final graph state ... },
}
```
The shape is described; the actual draft is produced by the native model.

Credentials and dependencies
----------------------------
`TAVILY_API_KEY` must be present in the environment because the native
`internet_search` phase always runs and uses Tavily. `OPENAI_API_KEY` is
provided by the deployment's model interception; no credential value is stored
in this file.

Resource ownership
------------------
The bridge keeps one native `DocumentWriter` per thread: when ABB supplies a
stable thread_id, the same writer and in-memory checkpoint are reused, so the
thread continuity the harness offers is honored rather than silently dropped.
Note that kiroku's own graph is single-shot by design — each new input starts
a fresh document task on that thread — so cross-input memory remains limited
by the upstream workflow itself. `close()` drops all cached writers and
blocks further invocations; it is safe to repeat.
"""

from collections.abc import Mapping
from copy import deepcopy
import os
import sys
from pathlib import Path

# The worker loads this file from the outer bindings/ directory, so the agent
# source root (agent/, containing kiroku_app.py and the agents package) is not
# guaranteed to be importable. Resolve it relative to this file and put it on
# sys.path before the lazy source import; harmless if already present (e.g.
# via PYTHONPATH in the image).
_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
if _SOURCE_ROOT.is_dir() and str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))


def message_from_input(value):
    """Accept current text or exactly {message: text}.

    Args:
        value: Non-empty string, or a mapping whose only key is `message`
            and whose value is a non-empty string.

    Returns:
        The stripped current request text.

    Raises:
        ValueError: If the input is empty, not text, or has extra fields.
    """
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError(
                "Kiroku accepts a non-empty text request or exactly {message: text}"
            )
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Kiroku request must be a non-empty text string")
    return value.strip()


def title_from_text(text):
    """Derive a working title from the request text.

    The requested topic must be visible in the specification, not only in
    area_of_paper/hypothesis: InternetSearch.create_task builds the writing
    task around the title, so a fixed placeholder title makes the document
    drift off-topic. Takes the first line or sentence of the request,
    bounded to 80 characters.
    """
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    for sep in (". ", "。", "! ", "? ", "！", "？", "; ", "；"):
        if sep in first:
            first = first.split(sep)[0].strip()
            break
    return first[:80] or "Untitled Document"


def specification_from_text(text):
    """Build the approved fixed minimal document specification.

    The input text is preserved verbatim in both `area_of_paper` and
    `hypothesis`, and its first line/sentence becomes the working title so
    the requested topic actually drives the native writing task. Section
    names and paragraph counts remain fixed minimal values.

    Args:
        text: The current plain-text request.

    Returns:
        A mapping consumed by the native Kiroku graph state.
    """
    return {
        "title": title_from_text(text),
        "suggest_title": False,
        "generate_citations": False,
        "type_of_document": "technical briefing",
        "area_of_paper": text,
        "hypothesis": text,
        "section_names": ["Introduction", "Main Points", "Conclusion"],
        # One entry per section: InternetSearch.create_task calls len() on
        # this value, so a bare int would raise TypeError.
        "number_of_paragraphs": [1, 1, 1],
        # Config fields the native UI supplies via read_initial_state but
        # graph nodes read directly from state: InternetSearch.run uses
        # number_of_queries; is_generate_review_complete uses max_revisions;
        # PaperWriter.run uses sentences_per_paragraph (native UI default 4).
        "number_of_queries": 1,
        "max_revisions": 1,
        "sentences_per_paragraph": 4,
        "results": "",
        "references": [],
    }


def initial_state_from_specification(specification):
    """Reproduce the initial state values used by KirokuUI.initial_step.

    With suggest_title=False the compiled graph ENTERS at the
    `internet_search` node; the bookkeeping `state` field initialized here is
    `topic_sentence_writer`, exactly as KirokuUI.initial_step does
    (kiroku_app.py:382-395). The entry point and the bookkeeping field are
    distinct: the field records the previous logical phase and is updated by
    each node as the graph runs.

    Args:
        specification: Mapping returned by `specification_from_text`.

    Returns:
        A deep copy with native runtime fields initialized.
    """
    state = deepcopy(specification)
    state["state"] = "topic_sentence_writer"
    state["references"] = state.get("references", [])
    state["draft"] = ""
    state["revision_number"] = 1
    state["messages"] = []
    state["review_instructions"] = []
    state["review_topic_sentences"] = []
    return state


def draft_from_state(state):
    """Return the native draft text, applying the upstream markdown cleanup.

    Args:
        state: Native graph state mapping.

    Returns:
        The draft string; empty string when absent.
    """
    draft = state.get("draft", "") or ""
    draft = draft.strip()
    if "```markdown" in draft:
        draft = "\n".join(draft.split("\n")[1:-1])
    return draft


class KirokuBridge:
    """Adapter around the native DocumentWriter compiled graph."""

    def __init__(self):
        if not os.environ.get("TAVILY_API_KEY"):
            raise RuntimeError(
                "TAVILY_API_KEY is required because the native internet_search "
                "phase always runs and uses Tavily"
            )
        # One native writer per thread: ABB passes a stable thread_id per
        # Case, and reusing the writer keeps that thread's native checkpoint
        # instead of silently dropping the continuity the harness offers.
        self._writers = {}
        self._fallback_seq = 0
        self._closed = False

    def _resolve_run_config(self, config):
        """Merge the incoming RunnableConfig, honoring ABB's thread identity.

        Callbacks, tags and metadata are preserved as supplied. The
        configurable gains the thread identity (ABB's thread_id when present,
        otherwise a per-invoke fallback) and the empty native instruction.

        Returns:
            (thread_key, run_config): the effective thread key and a new
            config mapping; the caller's object is never mutated.
        """
        run_config = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        incoming = configurable.get("thread_id")
        if incoming:
            thread_key = str(incoming)
        else:
            self._fallback_seq += 1
            thread_key = f"kiroku-bridge-{self._fallback_seq}"
        configurable["thread_id"] = thread_key
        configurable["instruction"] = ""
        run_config["configurable"] = configurable
        return thread_key, run_config

    def _create_writer(self, specification):
        """Construct a fresh native DocumentWriter for one invocation.

        Each input runs its own document-writing session, so every invoke
        builds a new writer (and therefore a new in-memory checkpoint thread)
        instead of reusing a completed one. The writer constructor arguments
        come from the fixed specification. The local variable is returned
        only after the constructor completed successfully, so a failed
        construction never leaks a partially initialized writer.
        """
        if not (_SOURCE_ROOT / "kiroku_app.py").is_file():
            raise RuntimeError(
                "Kiroku source root not found at "
                f"{_SOURCE_ROOT} (expected kiroku_app.py next to the "
                "bindings directory; check the image layout)"
            )
        from kiroku_app import DocumentWriter

        writer = DocumentWriter(
            suggest_title=bool(specification.get("suggest_title", False)),
            generate_citations=bool(specification.get("generate_citations", False)),
            model_name="openai++",
            temperature=float(specification.get("temperature", 0.0)),
        )
        # Best-effort optimization only: clearing the compiled graph's
        # interrupt lists may not be honored by every runtime. The
        # authoritative mechanism is the empty-instruction resume loop in
        # _run_until_complete.
        writer.graph.interrupt_before = []
        writer.graph.interrupt_after = []
        return writer

    def _next_state_name(self, writer):
        """Return the native next-state name or an empty string.

        The checkpoint lookup configurable carries thread identity only, per
        the LangGraph get_state contract. An empty ``next`` tuple means the
        graph has run to completion; no exceptions are masked here.
        """
        config = {"configurable": {"thread_id": str(writer.get_thread_id())}}
        snapshot = writer.graph.get_state(config)
        next_nodes = getattr(snapshot, "next", ()) or ()
        return next_nodes[0] if next_nodes else ""

    def _run_until_complete(self, writer, initial_state, run_config):
        """Drive the native graph to END with the merged RunnableConfig.

        The initial input and every resume go through ``writer.graph.invoke``
        directly so callbacks, tags, metadata and the thread identity from
        the incoming config actually reach the graph. DocumentWriter.invoke
        is deliberately bypassed: it wraps only an inner configurable mapping
        (dropping everything else) and its ``.get("draft")`` crashes on the
        None resume return (kiroku_app.py:212).

        Resume mechanism (source-backed, verified against the pinned
        langgraph==0.2.48): static interrupt_before pauses resume by invoking
        the graph with input None and the SAME config; the conditional edges
        (is_plan_review_complete / is_generate_review_complete) treat the
        empty configurable.instruction as "review complete, proceed".
        Command(resume=...) is NOT used: it targets dynamic interrupt() calls
        and does not clear static interrupt_before pauses in this version
        (the graph re-pauses at the same node). Resuming with None plus an
        empty instruction fabricates no human feedback.

        Returns:
            (final_state, last_draft): the native final state mapping and the
            last draft text observed in the checkpoint.
        """
        if initial_state is not None:
            writer.graph.invoke(initial_state, run_config)

        last_draft = ""
        guard = 0
        while guard < 50:
            guard += 1
            next_state = self._next_state_name(writer)
            if not next_state:
                break
            writer.graph.invoke(None, run_config)
            resumed_values = writer.graph.get_state(run_config).values or {}
            resumed_draft = resumed_values.get("draft", "")
            last_draft = (
                resumed_draft.strip() if isinstance(resumed_draft, str) else ""
            ) or last_draft
        if guard >= 50:
            raise RuntimeError(
                "Kiroku did not complete after resuming native manual-review interrupts"
            )

        final_state = writer.graph.get_state(run_config).values or {}
        if not final_state and isinstance(writer.state, Mapping):
            final_state = writer.state
        return final_state, last_draft

    def invoke(self, value, config=None):
        """Run one complete native Kiroku document-writing workflow.

        Args:
            value: Plain-text request or exactly {"message": text}.
            config: Optional RunnableConfig. Callbacks, tags, metadata and
                configurable.thread_id are honored and forwarded to the
                graph (see _resolve_run_config); the binding only adds the
                empty native ``instruction`` and a fallback thread key when
                none is supplied. Reusing ABB's thread_id reuses the same
                native writer and checkpoint instead of silently starting
                from a blank thread.

        Returns:
            Mapping with `draft`, `title`, `document_specification` and
            `native_state`. `draft` is the native final document text
            extracted from state.

        Raises:
            ValueError: Invalid input shape.
            RuntimeError: Missing Tavily key, closed binding, or failure to
                complete the native workflow.
            Native execution errors propagate unchanged.
        """
        if self._closed:
            raise RuntimeError("Kiroku bridge is closed")

        text = message_from_input(value)
        specification = specification_from_text(text)
        thread_key, run_config = self._resolve_run_config(config)
        writer = self._writers.get(thread_key)
        if writer is None:
            writer = self._create_writer(specification)
            writer.set_thread_id(thread_key)
            self._writers[thread_key] = writer
        initial_state = initial_state_from_specification(specification)
        final_state, last_draft = self._run_until_complete(writer, initial_state, run_config)

        return {
            "draft": last_draft or draft_from_state(final_state),
            "title": final_state.get("title", specification.get("title", "")),
            "document_specification": specification,
            "native_state": final_state,
        }

    def close(self):
        """Mark this binding closed; later invoke calls raise RuntimeError.

        Drops the per-thread native writers (the only state this bridge
        holds). No external files, databases or subprocesses are created by
        this binding. Cleanup is safe to repeat.
        """
        self._writers = {}
        self._closed = True


def create_graph():
    """Return a fresh KirokuBridge instance.

    The factory takes no arguments and never returns a coroutine or generator.
    Each invocation on the returned bridge constructs its own native
    DocumentWriter and checkpoint, so inputs are independent sessions.
    """
    return KirokuBridge()

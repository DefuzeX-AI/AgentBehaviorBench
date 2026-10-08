"""Bridge ABB's LangGraph adapter to the Podcast Agent's native creation graph.

Native entrypoint (evidence: src/utils/utils.py:195-232 and
src/utils/agents_and_workflows.py:19-30,156-167)

The upstream Agent runs its podcast pipeline as a LangGraph graph built by
``PodcastCreationWorkflow.create_workflow()``. That method returns an
UNCOMPILED ``StateGraph``; the ``compile()`` call belongs to the caller, and
the public caller is ``src/utils/utils.py:create_podcast()``, which does::

    workflow_obj = PodcastCreationWorkflow(...)
    workflow = workflow_obj.create_workflow()
    workflow = workflow.compile()
    state = PodcastState(main_text=HumanMessage(content=text),
                         key_points=None, script_essence=None,
                         enhanced_script=None)
    final_state = await workflow.ainvoke(state)

Graph shape (``summarizer -> scriptwriter -> enhancer -> END``), all three
nodes synchronous ``chain.invoke`` calls inside an async graph, no retry, no
fallback, no error handling. Each node raises ``ValueError`` when its input
field is empty, and the constructor raises ``FileNotFoundError`` when a prompt
file under ``prompts/`` is missing. Those behaviours are preserved unchanged.

Adaptations for the ABB boundary

* The SDK supplies plain text and the manifest declares no ``input_key``, so
  this binding receives the Case text directly and validates it. Upstream's
  production route (``fast_api_app.py`` ``/create_podcasts``) accepts a PDF
  upload and turns it into text through ``extract_text_from_pdf``; the PDF is
  only the transport for the text. The graph's own required input is
  ``PodcastState.main_text`` (``BaseMessage``), so the Case text is placed
  there verbatim and the PDF transport step is skipped. No business value is
  invented and no node is replaced.
* Model selection: ``PodcastCreationWorkflow`` takes ``summarizer_model``,
  ``scriptwriter_model`` and ``enhancer_model`` plus a ``provider`` string.
  With ``provider="OpenAI"`` it builds ``ChatOpenAI(model=..., api_key=...)
  `` and sets no ``base_url``, so model traffic goes to the endpoint ABB's
  interception layer owns. ``provider="OpenRouter"`` hardcodes
  ``base_url="https://openrouter.ai/api/v1"`` and would bypass the declared
  model route, so it is never used here. The three model ids are read from
  the environment (``PODCAST_SUMMARIZER_MODEL``, ``PODCAST_SCRIPTWRITER_MODEL``,
  ``PODCAST_ENHANCER_MODEL``); unset values fall back to the upstream default
  ``gpt-4o-mini``.
* ``config`` is forwarded to ``workflow.ainvoke`` so LangChain callbacks,
  tags, metadata and thread settings survive.
* The complete native ``PodcastState`` is returned and no ``output_key`` is
  configured, so ABB submits the whole mapping: ``main_text``, ``key_points``,
  ``script_essence``, ``enhanced_script``. Message bodies keep their native
  type; no answer text is manufactured.

Out of scope, and not claimed by this binding: TTS audio generation
(``src/paudio.py`` ``generate_tts``, which runs after the graph ends), PDF
upload and PyPDF2 extraction, the TextGrad prompt-optimisation loop, the
voting/feedback FastAPI routes and the React frontend.

Ownership: the binding owns the workflow object it builds per invocation and
holds no client, database or directory of its own. ``close``/``aclose`` only
mark the instance closed and are safe to repeat.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# This file is <unit>/bindings/podcast_workflow.py; the imported source lives
# under <unit>/agent. The upstream package imports itself both as
# "src.utils.agents_and_workflows" (fast_api_app.py) and as
# "utils.agents_and_workflows" (src/paudio.py), so the agent root must be on
# sys.path for the "src.*" form and agent/src for the bare form.
_AGENT_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "agent",
    Path(__file__).resolve().parents[1] / "agent" / "src",
)

# Upstream default model id (PodcastCreationWorkflow.__init__ signature).
_DEFAULT_MODEL = "gpt-4o-mini"

# Environment names that carry the three deployed model ids.
_MODEL_ENV = {
    "summarizer": "PODCAST_SUMMARIZER_MODEL",
    "scriptwriter": "PODCAST_SCRIPTWRITER_MODEL",
    "enhancer": "PODCAST_ENHANCER_MODEL",
}


def _ensure_native_import_root() -> None:
    """Put the native agent source roots on sys.path when present."""
    for candidate in _AGENT_ROOT_CANDIDATES:
        if candidate.is_dir():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)


def _deployed_model(role: str) -> str:
    """Return the deployed model id for one node role.

    Reads the environment at call time so a host-provided value is honoured;
    falls back to the upstream default when unset.
    """
    name = os.environ.get(_MODEL_ENV[role], "").strip()
    return name or _DEFAULT_MODEL


def _case_text(value: Any) -> str:
    """Validate one ABB Case input into the native main_text content.

    Args:
        value: Plain text, or a mapping whose ``main_text`` entry holds the
            text (the mapping form matches the native state field name so a
            structured Case can address it directly).

    Returns:
        The non-empty text to place in ``PodcastState.main_text``.

    Raises:
        ValueError: The input is neither text nor a mapping, carries unknown
            fields, or is empty/whitespace-only. Empty input is rejected here
            because the native ``run_summarizer`` would raise on it anyway;
            rejecting it in the binding keeps the failure attributable.
    """
    if isinstance(value, str):
        text = value
    elif isinstance(value, Mapping):
        unknown = sorted(set(value) - {"main_text"})
        if unknown:
            raise ValueError("Unsupported podcast input field(s): " + ", ".join(unknown))
        item = value.get("main_text")
        if item is None:
            raise ValueError("main_text is required")
        if not isinstance(item, str):
            raise ValueError("main_text must be a string")
        text = item
    else:
        raise ValueError("Input must be text or a mapping containing main_text")

    if not text.strip():
        raise ValueError("main_text must be non-empty text")
    return text


class PodcastBinding:
    """Run one podcast creation per ABB Case input and return its native state."""

    def __init__(self) -> None:
        self._closed = False

    async def ainvoke(self, value, config=None):
        """Execute the native graph and return the complete PodcastState.

        Args:
            value: Current Case input — plain text, or a mapping with a
                ``main_text`` string.
            config: LangChain ``RunnableConfig`` forwarded unchanged to the
                native graph. It is never serialized or replaced.

        Returns:
            The native ``PodcastState`` mapping with ``main_text``,
            ``key_points``, ``script_essence`` and ``enhanced_script``.

        Raises:
            ValueError: Unsupported or empty input.
            RuntimeError: The binding is closed.
            Exception: Any native graph/model failure propagates unchanged,
                including the upstream ``ValueError`` guards and the
                ``FileNotFoundError`` for a missing prompt file.
        """
        if self._closed:
            raise RuntimeError("Podcast binding is closed")

        text = _case_text(value)

        _ensure_native_import_root()
        from langchain_core.messages import HumanMessage
        from src.utils.agents_and_workflows import PodcastCreationWorkflow
        from src.utils.utils import PodcastState

        workflow_obj = PodcastCreationWorkflow(
            summarizer_model=_deployed_model("summarizer"),
            scriptwriter_model=_deployed_model("scriptwriter"),
            enhancer_model=_deployed_model("enhancer"),
            provider="OpenAI",
        )
        workflow = workflow_obj.create_workflow()
        workflow = workflow.compile()

        state = PodcastState(
            main_text=HumanMessage(content=text),
            key_points=None,
            script_essence=None,
            enhanced_script=None,
        )
        return await workflow.ainvoke(state, config=config)

    def invoke(self, value, config=None):
        """Synchronous entrypoint for callers without a running event loop.

        Bridges to :meth:`ainvoke`; BBA's async adapter prefers ``ainvoke``
        directly. Same input, config, return value and errors.
        """
        import asyncio

        return asyncio.run(self.ainvoke(value, config))

    def close(self) -> None:
        """Mark this instance closed. Idempotent; owns no external resources."""
        self._closed = True

    async def aclose(self) -> None:
        """Async cleanup hook; idempotent and equivalent to :meth:`close`."""
        self._closed = True


def create_graph():
    """Return a fresh :class:`PodcastBinding` for the ABB worker.

    Called with no arguments. Input example for one Case: a plain-text
    excerpt of an academic paper, or ``{"main_text": "..."}``.
    """
    return PodcastBinding()

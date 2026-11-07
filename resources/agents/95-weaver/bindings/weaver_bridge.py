"""ABB LangGraph binding for Weaver's research graph.

Weaver is a FastAPI-hosted LangGraph platform. The public native entrypoint is
``agent/core/graph.py:create_research_graph(checkpointer=None,
interrupt_before=None, store=None)``, which ``main.py`` bootstraps with a
checkpointer, a long-term memory store and ``settings.interrupt_nodes_list``.

This binding reproduces that bootstrap without running the FastAPI server:

1. Sets model-related environment defaults before the source modules import
   their settings singleton (pydantic-settings reads field-name env vars).
2. Imports ``create_research_graph`` and compiles the graph with a fresh
   ``langgraph.checkpoint.memory.MemorySaver``, ``interrupt_before=None`` and
   ``store=None``. With interrupts disabled the HITL review nodes no-op
   (they are guarded by ``_hitl_checkpoint_active``), so one invoke runs the
   graph to completion.
3. Maps the SDK text into the native ``AgentState.input`` field and runs a
   single invoke per Case step with a stable-per-step thread_id (the caller's
   RunnableConfig is forwarded; ``configurable.thread_id`` is injected when
   absent).

The SDK text is the user query; the graph's own LLM-based router decides
between direct answers, tool use and deep research. Deep/web routes need a
search-provider key (e.g. ``TAVILY_API_KEY``), which is optional for this
deployment: without it the agent must answer via the direct/agent routes and
report search failures honestly instead of fabricating results.
"""

from __future__ import annotations

import os
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig


def _apply_model_env_defaults() -> None:
    """Point Weaver's per-role model settings at the deployment model.

    Weaver's settings singleton reads field-name environment variables
    (pydantic-settings, case-insensitive): ``PRIMARY_MODEL``,
    ``REASONING_MODEL``, ``PLANNER_MODEL``, ``RESEARCHER_MODEL``,
    ``WRITER_MODEL``, ``EVALUATOR_MODEL``, ``CRITIC_MODEL``,
    ``TOOL_SELECTOR_MODEL``. Set them from ``LLM_MODEL`` when unset so the
    deployment model (and the harness replacement target behind it) is used
    consistently across roles.
    """
    model = os.environ.get("LLM_MODEL", "").strip()
    if not model:
        return
    for name in (
        "PRIMARY_MODEL",
        "REASONING_MODEL",
        "PLANNER_MODEL",
        "RESEARCHER_MODEL",
        "WRITER_MODEL",
        "EVALUATOR_MODEL",
        "CRITIC_MODEL",
        "TOOL_SELECTOR_MODEL",
    ):
        os.environ.setdefault(name, model)


class WeaverResearchGraph:
    """Binding wrapper around Weaver's compiled research graph."""

    def __init__(self) -> None:
        self._native: object | None = None
        self._closed = False

    def _load_native(self) -> object:
        if self._native is not None:
            return self._native

        _apply_model_env_defaults()

        from langgraph.checkpoint.memory import MemorySaver

        from agent.core.graph import create_research_graph

        self._native = create_research_graph(
            checkpointer=MemorySaver(),
            interrupt_before=None,
            store=None,
        )
        return self._native

    @staticmethod
    def _thread_config(config: RunnableConfig | None) -> dict:
        merged: dict = dict(config) if isinstance(config, dict) else {}
        configurable = dict(merged.get("configurable") or {})
        if not configurable.get("thread_id"):
            configurable["thread_id"] = str(uuid4())
        merged["configurable"] = configurable
        return merged

    def invoke(self, value, config: RunnableConfig | None = None):
        """Run one research invocation and return the final graph state."""
        if self._closed:
            raise RuntimeError("WeaverResearchGraph is closed")

        if isinstance(value, dict):
            text = value.get("input")
            if text is None:
                raise ValueError("Input mapping must contain 'input'")
            extra = set(value) - {"input", "images"}
            if extra:
                raise ValueError(f"Unsupported input fields: {sorted(extra)}")
        else:
            text = value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("input must be a non-empty string")

        native = self._load_native()
        return native.invoke({"input": text.strip()}, config=self._thread_config(config))

    def close(self) -> None:
        self._native = None
        self._closed = True


def create_graph():
    """Zero-argument factory required by the ABB langgraph adapter."""
    return WeaverResearchGraph()
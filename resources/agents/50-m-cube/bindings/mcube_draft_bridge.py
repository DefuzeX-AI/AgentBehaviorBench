"""BBA LangGraph binding for M-Cube's patent-drafting workflow.

Native entrypoint
-----------------
The public LangGraph workflow is compiled by
`workflows.draft_workflow.build_draft_workflow(bundle, checkpointer)`.
The source FastAPI runtime builds the same agent bundle and a MemorySaver
_checkpointer in `api/routers._build_draft_graph_for_runtime`.

This binding reproduces that bootstrap without running the FastAPI server:

1. Disable the source's .env loader by setting ``MCUBE_DISABLE_DOTENV=1``
   before importing any source modules (mirrors the guard in main.py).
2. Build an LLM callable through ``services.llm_factory.build_llm_callable``
   with the fixed OpenAI-compatible provider and the model names injected via
   ``LLM_MODEL`` / ``LLM_VISION_MODEL``.  If the factory cannot build a real
   callable it returns ``None`` (deterministic stub fallback).  The binding
   treats this as a hard error because stub output is forbidden for
   certification.
3. Construct the same ``DraftAgentBundle`` of ``BaseStructuredAgent`` agents as
   the source runtime and compile the graph with a fresh
   ``langgraph.checkpoint.memory.MemorySaver``.
4. Invoke the graph starting from ``{"disclosure_text": <case_text>}`` and a
   per-run ``thread_id``.
5. The workflow contains three HITL interrupt sites.  For a one-shot SDK
   invoke the binding automatically resumes them with the authorized payloads
   documented in the onboarding answers, looping until no ``__interrupt__``
   remains, then returns the final state.

Input
-----
SDK text is wrapped by ``input_key = "disclosure_text"`` into
``{"disclosure_text": <non-empty string>}``.  The binding also accepts a
mapping that already contains ``disclosure_text`` and optional
``model_name``/``session_id``/``trace_id`` fields; unknown keys are rejected.

Output
------
The complete final ``DraftingState`` dictionary produced by the compiled
LangGraph, including ``status``, ``claims``, ``specification``,
``claim_traceability``, etc.

Config
------
RunnableConfig is forwarded to the native graph.  The binding injects a fresh
``thread_id`` if the config has no ``configurable.thread_id``.

Owned resources
---------------
A fresh ``MemorySaver`` is created per binding instance and is released when the
binding is closed.  No persistent files are written by the binding.

Example input
-------------
"Draft a patent for a solar-powered mobile charger that uses a flexible
photovoltaic panel and a lithium-polymer battery with overcharge protection."
"""
from __future__ import annotations

import os
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig


# Disable the source's automatic .env loader before any source module is
# imported.  See main.py: the guard variable stops load_dotenv from running.
os.environ.setdefault("MCUBE_DISABLE_DOTENV", "1")

from agents.base_agent import BaseStructuredAgent, RetryPolicy  # noqa: E402
from agents.drafter_agents import DraftingState  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from models.draft_schemas import (  # noqa: E402
    ClaimTraceabilityReport,
    ClaimsSet,
    ClaimsSetRevision,
    Specification,
    TechSummary,
)
from models.image_schemas import DrawingMap  # noqa: E402
from models.review_schemas import ReviewReport  # noqa: E402
from services.llm_factory import build_llm_callable  # noqa: E402
from workflows.draft_workflow import DraftAgentBundle, build_draft_workflow  # noqa: E402


def _text_from_input(value: object) -> str:
    """Accept text or exactly {'disclosure_text': text}; reject other shapes."""
    if isinstance(value, dict):
        if set(value) - {"disclosure_text", "model_name", "session_id", "trace_id"}:
            raise ValueError(
                "Input mapping may only contain disclosure_text and optional "
                "model_name/session_id/trace_id fields"
            )
        if "disclosure_text" not in value:
            raise ValueError("Input mapping must contain disclosure_text")
        text = value["disclosure_text"]
    else:
        text = value
    if not isinstance(text, str) or not text.strip():
        raise ValueError("disclosure_text must be a non-empty string")
    return text.strip()


def _state_from_input(value: object) -> DraftingState:
    """Build the initial DraftingState from the SDK input."""
    if isinstance(value, dict):
        extra = set(value) - {"disclosure_text", "model_name", "session_id", "trace_id"}
        if extra:
            raise ValueError(f"Unsupported input fields: {sorted(extra)}")
        if "disclosure_text" not in value:
            raise ValueError("Input mapping must contain disclosure_text")
        text = value["disclosure_text"]
    else:
        text = value
    if not isinstance(text, str) or not text.strip():
        raise ValueError("disclosure_text must be a non-empty string")

    state: DraftingState = {"disclosure_text": text.strip()}
    if isinstance(value, dict):
        if "model_name" in value:
            state["model_name"] = value["model_name"]
        if "session_id" in value:
            state["session_id"] = value["session_id"]
        if "trace_id" in value:
            state["trace_id"] = value["trace_id"]
    return state


class MCubeDraftGraph:
    """Binding wrapper around M-Cube's compiled patent-drafting workflow."""

    def __init__(self) -> None:
        self._native: object | None = None
        self._closed = False

    def _load_native(self) -> object:
        if self._native is not None:
            return self._native

        llm_model = os.environ.get("LLM_MODEL", "").strip()
        llm_vision_model = os.environ.get("LLM_VISION_MODEL", "").strip()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()

        if not llm_model:
            raise ValueError("LLM_MODEL must be supplied in the environment")
        if not llm_vision_model:
            raise ValueError("LLM_VISION_MODEL must be supplied in the environment")
        if not api_key:
            raise ValueError("OPENAI_API_KEY must be supplied in the environment")

        # base_url=None lets llm_factory default to https://api.openai.com/v1,
        # which is the only host covered by the interception route.
        llm_callable = build_llm_callable(
            provider="openai",
            model=llm_model,
            vision_model=llm_vision_model,
            base_url=None,
            api_key=api_key,
            temperature=None,
        )
        if llm_callable is None:
            raise RuntimeError(
                "build_llm_callable returned None; refusing to run the "
                "deterministic stub fallback. Check LLM_MODEL/LLM_VISION_MODEL/OPENAI_API_KEY."
            )

        bundle = DraftAgentBundle(
            extract_tech_agent=BaseStructuredAgent[TechSummary](
                name="extract_tech_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            draft_claims_agent=BaseStructuredAgent[ClaimsSet](
                name="draft_claims_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            traceability_agent=BaseStructuredAgent[ClaimTraceabilityReport](
                name="traceability_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            write_spec_agent=BaseStructuredAgent[Specification](
                name="write_spec_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            logic_review_agent=BaseStructuredAgent[ReviewReport](
                name="logic_review_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            revise_claims_agent=BaseStructuredAgent[ClaimsSetRevision](
                name="revise_claims_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
            drawing_analyzer_agent=BaseStructuredAgent[DrawingMap](
                name="drawing_analyzer_agent",
                llm_callable=llm_callable,
                retry_policy=RetryPolicy(max_retries=3),
            ),
        )

        # MemorySaver is the same checkpoint class used by the source runtime.
        checkpointer = MemorySaver()
        self._native = build_draft_workflow(bundle, checkpointer=checkpointer)
        return self._native

    @staticmethod
    def _thread_config(config: RunnableConfig | None) -> tuple[str, dict]:
        """Return a stable thread_id and the config dict to pass to the graph."""
        thread_id = None
        if isinstance(config, dict) and isinstance(config.get("configurable"), dict):
            thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            thread_id = str(uuid4())
        return thread_id, {"configurable": {"thread_id": thread_id}}

    def invoke(self, value, config=None):
        """Run one patent-drafting invocation and return the final state.

        Args:
            value: SDK text or {"disclosure_text": <text>, ...}.
            config: LangChain RunnableConfig; forwarded to the native graph.

        Returns:
            The final DraftingState dictionary from the compiled graph after
            auto-resuming all HITL interrupts.
        """
        if self._closed:
            raise RuntimeError("MCubeDraftGraph is closed")

        native = self._load_native()
        initial_state = _state_from_input(value)
        thread_id, run_config = self._thread_config(config)

        result = native.invoke(initial_state, config=run_config)

        # Auto-resume HITL interrupts. The source workflow interrupts at
        # human_review, claims_revise_review, and spec_review.  For a one-shot
        # benchmark run we choose the authorized auto-resume payloads.
        from langgraph.types import Command  # local import keeps top-level light

        while isinstance(result, dict) and "__interrupt__" in result:
            interrupts = result["__interrupt__"]
            if not interrupts:
                break

            # Use the latest interrupt for payload inspection.
            interrupt_payload = interrupts[-1]
            if isinstance(interrupt_payload, dict) and "value" in interrupt_payload:
                payload = interrupt_payload["value"]
            else:
                payload = interrupt_payload

            event = None
            if isinstance(payload, dict):
                event = payload.get("event")

            if event == "claims_revision_required":
                resume_payload = {"apply_auto_claim_revision": True}
            elif event == "spec_review_required":
                resume_payload = {"apply_targeted_revision": True}
            else:
                # human_review or fallback: approve the generated claims verbatim.
                current_values = native.get_state(run_config)
                current_state = current_values.values if current_values else {}
                claims = current_state.get("claims") if isinstance(current_state, dict) else None
                resume_payload = {"approved_claims": claims}

            result = native.invoke(
                Command(resume=resume_payload),
                config=run_config,
            )

        return result

    def close(self) -> None:
        """Release owned resources.  Safe to call repeatedly."""
        self._closed = True
        self._native = None


def create_graph():
    """Factory returning a fresh M-Cube draft binding.

    Example input: "A solar-powered mobile charger with a flexible PV panel..."
    Example input (mapping): {"disclosure_text": "...", "model_name": "kimi-k3"}
    """
    return MCubeDraftGraph()

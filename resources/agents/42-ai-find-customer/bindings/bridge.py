"""Bridge ABB's LangGraph adapter to AI Hunter's native hunt pipeline.

Native entrypoint (evidence: backend/api/routes.py, ``_run_hunt``): AI Hunter
runs its B2B lead-hunting workflow as a LangGraph graph produced by
``graph.builder.build_graph`` from the node callbacks in ``agents.*``
(``parse_description_node``, ``insight_node``, ``keyword_gen_node``,
``search_node``, ``lead_extract_node``, ``email_craft_node``) plus the control
functions ``evaluate_progress`` and ``should_continue_hunting`` from
``graph.evaluate``. The upstream FastAPI route converts a ``HuntRequest`` into
a full initial state, drives the compiled graph with ``graph.astream(...)``,
accumulates every node update and finally attaches the native ``cost_summary``.
This binding reproduces that public lifecycle in-process: same graph, same
initial state, same accumulation, same final fields. It does not start the
FastAPI server, the headless worker or any CLI, and it does not replace the
Agent's search, scraping or LLM tools.

Adaptations for the ABB boundary:

* The SDK supplies text and the manifest sets ``input_key = "description"``, so
  BBA delivers ``{"description": <current case text>}``. The binding validates
  that shape (and additionally accepts the native ``HuntRequest`` field names
  as an explicit mapping) and places the complete text into the native
  free-form ``description`` field.

* Deployment bounds: the upstream ``HuntRequest`` defaults drive a ten-round
  hunt (``max_rounds=10``) toward 200 leads, which does not terminate inside an
  evaluation window. This deployment therefore uses single-round bounds
  (``target_lead_count=1``, ``max_rounds=1``,
  ``min_new_leads_threshold=1``) as its declared operating envelope; a mapping
  input can still request different bounds within the native field ranges.
  No value is inferred or invented beyond those declared defaults.
* A fresh native ``hunt_id`` (``uuid.uuid4()``) is generated per invocation,
  mirroring the upstream route.
* ``config`` is forwarded to ``graph.astream`` so LangChain/LangGraph
  callbacks, tags, metadata and thread settings survive.
* SSE broadcast, hunt persistence, progress callbacks and cancellation belong
  to the upstream API/UI layer and are intentionally not reproduced here; the
  graph execution and its completion semantics are unchanged.

Resource ownership: this binding owns no database, client or directory of its
own. The compiled graph and the Agent's clients are created and released by the
native modules per invocation. ``close``/``aclose`` only mark the instance
closed and are safe to repeat.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# This file is <unit>/bindings/bridge.py; the imported source lives under
# <unit>/agent/backend (source_root is "agent/", backend package root inside
# it). Resolve the native import root relative to this file so execution does
# not depend on the worker's current working directory.
_BACKEND_ROOT_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "agent" / "backend",
    Path(__file__).resolve().parents[1] / "backend",
)

# Deployment operational bounds for this ABB unit. The upstream HuntRequest
# defaults (backend/api/routes.py) are target_lead_count=200, max_rounds=10 and
# min_new_leads_threshold=5, which drive an unbounded ten-round hunt with a
# candidate budget of 20 URLs per round. The approved onboarding plan requires
# explicit bounded deployment settings, so this unit declares single-round
# bounds: one round, target one lead, threshold one new lead. Callers may still
# override any of them through the mapping input; the defaults below are the
# deployment's intended operating envelope, recorded in requirement.md.
_DEFAULT_TARGET_LEAD_COUNT = 1
_DEFAULT_MAX_ROUNDS = 1
_DEFAULT_MIN_NEW_LEADS_THRESHOLD = 1

# Native HuntRequest fields accepted as an explicit mapping input.
_HUNT_REQUEST_FIELDS = frozenset(
    {
        "website_url",
        "description",
        "product_keywords",
        "target_customer_profile",
        "target_regions",
        "uploaded_file_ids",
        "target_lead_count",
        "max_rounds",
        "min_new_leads_threshold",
        "enable_email_craft",
        "email_template_examples",
        "email_template_notes",
        "template_seed",
    }
)


def _bool_field(item: Any) -> bool:
    """Accept only a real boolean for the native email-craft switch."""
    if item is None:
        return False
    if not isinstance(item, bool):
        raise ValueError("enable_email_craft must be a boolean")
    return item


def _seed_field(item: Any) -> dict[str, Any] | None:
    """Normalize the optional native template_seed mapping."""
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise ValueError("template_seed must be a mapping when provided")
    return dict(item)


def hunt_request_from_input(value: Any) -> dict[str, Any]:
    """Validate one ABB Case input into native HuntRequest-equivalent fields.

    Args:
        value: Plain text (the SDK text boundary; BBA wraps it into
            ``{"description": text}`` through ``input_key = "description"``),
            the mapping ``{"description": text}``, or a mapping using the
            native ``HuntRequest`` field names to override optional defaults.

    Returns:
        A dict containing every native request field, with upstream defaults
        filled in for anything not supplied.

    Raises:
        ValueError: The input is neither text nor a mapping; it contains
            unknown fields (never silently dropped); a field has the wrong type
            or an out-of-range value; or it supplies no hunting signal (the
            upstream headless worker likewise requires ``description``,
            ``website_url`` or ``product_keywords``).
    """
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("description must be non-empty text")
        raw: dict[str, Any] = {"description": value}
    elif isinstance(value, Mapping):
        unknown = sorted(set(value) - _HUNT_REQUEST_FIELDS)
        if unknown:
            raise ValueError("Unsupported hunt request field(s): " + ", ".join(unknown))
        raw = dict(value)
    else:
        raise ValueError("Input must be text or a mapping of hunt request fields")

    def text_field(name: str) -> str:
        item = raw.get(name, "")
        if item is None:
            return ""
        if not isinstance(item, str):
            raise ValueError(f"{name} must be a string")
        return item

    def str_list(name: str) -> list[str]:
        item = raw.get(name, [])
        if item is None:
            return []
        if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
            raise ValueError(f"{name} must be a list of strings")
        return list(item)

    def bounded_int(name: str, default: int, low: int, high: int) -> int:
        item = raw.get(name, default)
        if item is None:
            return default
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{name} must be an integer")
        if not low <= item <= high:
            raise ValueError(f"{name} must be between {low} and {high}")
        return item

    request = {
        "website_url": text_field("website_url"),
        "description": text_field("description"),
        "product_keywords": str_list("product_keywords"),
        "target_customer_profile": text_field("target_customer_profile"),
        "target_regions": str_list("target_regions"),
        "uploaded_file_ids": str_list("uploaded_file_ids"),
        "target_lead_count": bounded_int(
            "target_lead_count", _DEFAULT_TARGET_LEAD_COUNT, 1, 10000
        ),
        "max_rounds": bounded_int("max_rounds", _DEFAULT_MAX_ROUNDS, 1, 50),
        "min_new_leads_threshold": bounded_int(
            "min_new_leads_threshold", _DEFAULT_MIN_NEW_LEADS_THRESHOLD, 1, 100
        ),
        "enable_email_craft": _bool_field(raw.get("enable_email_craft", False)),
        "email_template_examples": str_list("email_template_examples"),
        "email_template_notes": text_field("email_template_notes"),
        "template_seed": _seed_field(raw.get("template_seed")),
    }

    if (
        not request["description"].strip()
        and not request["website_url"].strip()
        and not request["product_keywords"]
    ):
        raise ValueError(
            "A hunt needs a description, website_url or product_keywords; "
            "no hunting signal was supplied"
        )
    return request


def _ensure_native_import_root() -> None:
    """Put the native backend package root on sys.path when it is present."""
    for candidate in _BACKEND_ROOT_CANDIDATES:
        if candidate.is_dir():
            root = str(candidate)
            if root not in sys.path:
                sys.path.insert(0, root)
            return


def _load_native_graph():
    """Build the real compiled LangGraph pipeline used by the upstream route."""
    _ensure_native_import_root()
    from agents.email_craft_agent import email_craft_node
    from agents.insight_agent import insight_node
    from agents.keyword_gen_agent import keyword_gen_node
    from agents.lead_extract_agent import lead_extract_node
    from agents.parse_description_agent import parse_description_node
    from agents.search_agent import search_node
    from graph.builder import build_graph
    from graph.evaluate import evaluate_progress, should_continue_hunting

    return build_graph(
        parse_description_node=parse_description_node,
        insight_node=insight_node,
        keyword_gen_node=keyword_gen_node,
        search_node=search_node,
        lead_extract_node=lead_extract_node,
        evaluate_node=evaluate_progress,
        should_continue_fn=should_continue_hunting,
        email_craft_node=email_craft_node,
    )


def _initial_state(request: dict[str, Any], hunt_id: str) -> dict[str, Any]:
    """Build the native graph initial state exactly like ``_run_hunt``."""
    template_seed = request["template_seed"]
    return {
        "website_url": request["website_url"],
        "description": request["description"],
        "product_keywords": list(request["product_keywords"]),
        "target_customer_profile": request["target_customer_profile"],
        "target_regions": list(request["target_regions"]),
        "uploaded_files": list(request["uploaded_file_ids"]),
        "target_lead_count": request["target_lead_count"],
        "max_rounds": request["max_rounds"],
        "min_new_leads_threshold": request["min_new_leads_threshold"],
        "enable_email_craft": request["enable_email_craft"],
        "email_template_examples": list(request["email_template_examples"]),
        "email_template_notes": request["email_template_notes"],
        "template_seed": dict(template_seed) if template_seed else None,
        "insight": None,
        "keywords": [],
        "used_keywords": [],
        "search_results": [],
        "seen_urls": [],
        "matched_platforms": [],
        "keyword_search_stats": {},
        "leads": [],
        "email_sequences": [],
        "hunt_round": 1,
        "prev_round_lead_count": 0,
        "round_feedback": None,
        "current_stage": "start",
        "hunt_id": hunt_id,
        "messages": [],
    }


def _finalize_native_cost(hunt_id: str, accumulated: dict[str, Any]) -> None:
    """Attach the native cost summary exactly like the upstream ``_run_hunt``."""
    from observability.cost_tracker import get_tracker, remove_tracker

    accumulated["cost_summary"] = get_tracker(hunt_id).to_summary()
    remove_tracker(hunt_id)


def _discard_native_cost_tracker(hunt_id: str) -> None:
    """Release the native per-hunt cost tracker when execution fails."""
    try:
        from observability.cost_tracker import remove_tracker

        remove_tracker(hunt_id)
    except Exception:  # cleanup must never mask the original native failure
        pass


class HunterBinding:
    """Run one AI Hunter hunt per ABB Case input and return its native state."""

    def __init__(self) -> None:
        self._closed = False

    async def ainvoke(self, value, config=None):
        """Execute the native pipeline and return the merged final state.

        Args:
            value: Current Case input — text (wrapped by BBA into
                ``{"description": text}`` through ``input_key = "description"``)
                or a mapping using the native ``HuntRequest`` field names.
                Unknown fields are rejected, never silently dropped.
            config: LangChain ``RunnableConfig`` forwarded to
                ``graph.astream`` so callbacks, tags, metadata and thread
                settings survive. It is never serialized or replaced.

        Returns:
            The accumulated native graph state (``insight``, ``keywords``,
            ``used_keywords``, ``search_results``, ``leads``,
            ``email_sequences``, ``round_feedback``, ``keyword_search_stats``,
            ``hunt_round``, ``current_stage``, ``cost_summary``, ...). No
            ``output_key`` is configured, so this whole mapping is ABB's
            output. Lead records keep their native shape; no answer text is
            manufactured.

        Raises:
            ValueError: Unsupported or incomplete input.
            RuntimeError: The binding is closed.
            Exception: Any native graph/tool failure propagates unchanged;
                partial state is never returned as success.

        Example:
            ``await ainvoke({"description": "Find electrical distributors in
            the United States that may buy micro switches"})`` returns a
            mapping whose ``leads`` list holds the native lead records
            (company name, website, emails and similar fields).
        """
        if self._closed:
            raise RuntimeError("AI Hunter binding is closed")
        request = hunt_request_from_input(value)
        graph = _load_native_graph()
        hunt_id = str(uuid.uuid4())
        initial_state = _initial_state(request, hunt_id)
        accumulated: dict[str, Any] = dict(initial_state)
        try:
            async for chunk in graph.astream(initial_state, config=config):
                for node_name, node_output in chunk.items():
                    if node_name == "__end__":
                        continue
                    accumulated.update(node_output)
        except BaseException:
            _discard_native_cost_tracker(hunt_id)
            raise
        _finalize_native_cost(hunt_id, accumulated)
        return accumulated

    def invoke(self, value, config=None):
        """Synchronous entrypoint for callers without a running event loop.

        Bridges to :meth:`ainvoke` with ``asyncio.run``; BBA's async adapter
        prefers ``ainvoke`` directly. Same input, config, return value and
        errors as ``ainvoke``.
        """
        return asyncio.run(self.ainvoke(value, config))

    def close(self) -> None:
        """Mark this instance closed. Idempotent; owns no external resources."""
        self._closed = True

    async def aclose(self) -> None:
        """Async cleanup hook; idempotent and equivalent to :meth:`close`."""
        self._closed = True


def create_graph():
    """Return a fresh :class:`HunterBinding` for the ABB worker.

    Called with no arguments. Input example for one Case: ``{"description":
    "Find electrical distributors in the United States that may buy micro
    switches"}`` (plain text is wrapped the same way by the adapter's
    ``input_key = "description"``).
    """
    return HunterBinding()

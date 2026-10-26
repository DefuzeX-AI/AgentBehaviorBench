"""ABB binding for Aryan-Pardeshi/DeepResearch_AI (CiteProof Research, DeepSearch mode).

Native contract (source under ``agent/`` is unchanged):

1. **Entrypoint.** The FastAPI backend (``backend/app/api/agent.py``) drives the
   DeepSearch graph from ``backend/app/graph/builder.py`` in two calls:
   ``POST /research/start`` streams ``{"query": ..., "search_topic": ["all"]}``
   on a new ``thread_id`` until the ``approval`` node interrupts, then returns
   the problem statement (``ps``), ``plan``, ``status`` and ``error``;
   ``POST /research/approve`` streams ``Command(resume={"message": ...})`` on
   that thread and returns ``final_answer`` and ``citations`` when the graph
   completes, or the revised plan when the message asked for changes. The
   binding makes the same two calls without the HTTP/SSE layer.
   ``langgraph.json`` is not used: it points at ``./research-bot/backend/...``,
   which does not exist in the repository.

2. **Turns.** The first Case input is the research query. While the thread
   waits at the plan-approval interrupt, the next input is the user's reply to
   the plan (approval or requested changes). After the graph ends (completed or
   rejected by the query validator), a further input starts a new research
   thread, as a new ``/research/start`` would.

3. **Model and tools.** ``backend/app/llm.py`` builds ``ChatOpenAI`` from
   ``LLM_BASE_URL`` and ``LLM_API_KEY``; the image sets ``LLM_BASE_URL`` to the
   intercepted OpenAI route and ABB supplies the credential. Researchers search
   with Tavily (``TAVILY_API_KEY``). The aggregator may call
   ``generate_matplotlib_chart``, which writes PNG files under ``FIGURES_DIR``.

4. **Configuration.** ABB's config is merged with the native
   ``configurable.thread_id`` and passed to ``astream`` / ``aget_state``.

Output: ``{"answer": <text shown to the user>, "status", "ps", "plan",
"final_answer", "citations", "error", "thread_id"}``. Native exceptions
propagate.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
SEARCH_TOPIC = ["all"]  # ResearchStartRequest default


def _text(value) -> str:
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply text or exactly {'message': text}")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case input must be a non-empty message")
    return value


def _render(values: dict, awaiting: bool) -> str:
    if values.get("error"):
        return f"Error: {values['error']}"
    if awaiting:
        plan = values.get("plan") or []
        steps = "\n".join(f"{i}. {task}" for i, task in enumerate(plan, 1))
        return (f"Problem statement: {values.get('ps') or ''}\n\nResearch plan:\n{steps}\n\n"
                "Reply to approve this plan or describe the changes you want.")
    answer = values.get("final_answer") or ""
    citations = values.get("citations") or []
    if citations:
        answer += "\n\nCitations:\n" + "\n".join(f"- {c}" for c in dict.fromkeys(citations))
    return answer


class DeepSearchSession:
    def __init__(self):
        self._graph = None
        self._thread_id: str | None = None
        self._base: str | None = None

    def _ensure_graph(self):
        if self._graph is None:
            if str(SOURCE_ROOT) not in sys.path:
                sys.path.insert(0, str(SOURCE_ROOT))
            from backend.app.graph.builder import get_research_graph
            self._graph = get_research_graph()
        return self._graph

    async def ainvoke(self, value, config=None):
        text = _text(value)
        graph = self._ensure_graph()
        from langgraph.types import Command

        if self._base is None:
            case_thread = ((config or {}).get("configurable") or {}).get("thread_id")
            self._base = str(case_thread or uuid.uuid4().hex)

        awaiting = False
        if self._thread_id is not None:
            snapshot = await graph.aget_state(self._run_config(config))
            awaiting = bool(snapshot.next)
        if awaiting:
            payload = Command(resume={"message": text})
        else:
            self._thread_id = f"{self._base}-{uuid.uuid4().hex[:8]}"
            payload = {"query": text, "search_topic": list(SEARCH_TOPIC)}

        run_config = self._run_config(config)
        async for _ in graph.astream(payload, config=run_config):
            pass
        snapshot = await graph.aget_state(run_config)
        values = dict(snapshot.values)
        waiting = bool(snapshot.next)
        return {
            "answer": _render(values, waiting),
            "status": values.get("status"),
            "ps": values.get("ps"),
            "plan": values.get("plan"),
            "final_answer": values.get("final_answer"),
            "citations": list(dict.fromkeys(values.get("citations") or [])),
            "error": values.get("error"),
            "thread_id": self._thread_id,
        }

    def _run_config(self, config):
        run_config = dict(config or {})
        run_config["configurable"] = {**(run_config.get("configurable") or {}), "thread_id": self._thread_id}
        return run_config

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    def close(self):
        self._graph = None


def create_graph():
    """Return a fresh session; example input: 'Research recent advances in solid-state batteries for EVs'."""
    return DeepSearchSession()

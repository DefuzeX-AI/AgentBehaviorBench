"""ABB text boundary for LearningCircuit/local-deep-research.

Upstream entrypoint: ``local_deep_research.api.quick_summary`` (the documented programmatic API),
run with the upstream default research strategy ``langgraph-agent``. That strategy builds a
LangChain 1.x ``create_agent`` (a LangGraph graph) with ``web_search`` and ``research_subtopic``
tools; ``research_subtopic`` spawns parallel ``create_agent`` sub-agents. The upstream source under
``agent/`` is unchanged.

Deployment settings (all upstream settings keys, applied through ``create_settings_snapshot``):
- ``llm.provider = openai``: ChatOpenAI against api.openai.com, which ABB intercepts and routes to
  the configured target model.
- ``search.tool = wikipedia``, ``policy.egress_scope = public_only`` and every other
  ``search.engine.web.<engine>.agent_enabled = false``: the only search source is the keyless
  Wikipedia engine; no other engines are offered to the agent as specialized tools. (``strict``
  scope is not usable here: upstream denies every public host under it, including Wikipedia.)
- ``search.fetch.mode = disabled``: the upstream switch that removes the ``fetch_content`` tool
  (arbitrary-URL page fetches are outside this deployment's egress allow-list).
- Research budget lowered (agent iterations 15, sub-agent iterations 5, 2 parallel sub-agents,
  10 results per search) so one Case step completes within the container timeout.

The Case Input is the research query; the reply is the upstream ``summary`` (the report text
``quick_summary`` returns). Sources and formatted findings are kept in the raw output.
"""
import os
import uuid
from collections.abc import Mapping


SETTINGS_OVERRIDES = {
    "llm.provider": "openai",
    "search.tool": "wikipedia",
    "search.search_strategy": "langgraph-agent",
    "policy.egress_scope": "public_only",
    "search.fetch.mode": "disabled",
    # Bounded research budget (upstream defaults: 50 / 8 / 4 / 50 / 20) so one Case step fits the
    # container timeout; same settings a user lowers in the LDR settings page.
    "langgraph_agent.max_iterations": 15,
    "langgraph_agent.max_sub_iterations": 5,
    "langgraph_agent.max_subagent_workers": 2,
    "search.max_results": 10,
    "search.engine.web.wikipedia.default_params.max_results": 10,
}


class LocalDeepResearchGraph:
    def __init__(self):
        self._closed = False

    def invoke(self, value, config=None, **kwargs):
        from langchain_core.runnables import RunnableLambda

        return RunnableLambda(self._run, name="local_deep_research.quick_summary").invoke(value, config=config)

    async def ainvoke(self, value, config=None, **kwargs):
        # Deliberately synchronous on the calling (main) thread. Upstream's programmatic API is
        # synchronous and its @no_db_settings guard (utilities/db_utils.get_db_session) refuses any
        # non-"MainThread" caller without a web request context, so offloading to a worker thread
        # (asyncio.to_thread) fails with "Database access attempted from background thread". The
        # oneshot container runs exactly one Case, so blocking its event loop is harmless.
        return self.invoke(value, config=config, **kwargs)

    def _run(self, value):
        from local_deep_research.api import quick_summary
        from local_deep_research.api.settings_utils import create_settings_snapshot

        query = value.get("query") if isinstance(value, Mapping) else value
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Supply the Case Input as a non-empty research query")
        overrides = dict(SETTINGS_OVERRIDES)
        overrides["llm.model"] = os.environ.get("LDR_LLM_MODEL", "gpt-4o-mini")
        overrides["llm.openai.api_key"] = os.environ["OPENAI_API_KEY"]
        snapshot = create_settings_snapshot(overrides=overrides)
        for key, setting in snapshot.items():
            if (key.startswith("search.engine.web.") and key.endswith(".agent_enabled")
                    and key != "search.engine.web.wikipedia.agent_enabled" and isinstance(setting, dict)):
                setting["value"] = False
        result = quick_summary(
            query,
            research_id=str(uuid.uuid4()),
            settings_snapshot=snapshot,
            search_tool="wikipedia",
            search_strategy="langgraph-agent",
        )
        summary = result.get("summary") if isinstance(result, Mapping) else None
        if not isinstance(summary, str) or not summary.strip():
            # quick_summary folds strategy errors into formatted_findings ("Error: ...").
            detail = result.get("formatted_findings") if isinstance(result, Mapping) else result
            raise RuntimeError(f"local-deep-research returned no summary: {detail!r}"[:2000])
        return {
            "answer": summary,
            "sources": result.get("sources", []),
            "formatted_findings": result.get("formatted_findings", ""),
            "research_id": result.get("research_id"),
        }

    def close(self):
        self._closed = True


def create_graph():
    return LocalDeepResearchGraph()

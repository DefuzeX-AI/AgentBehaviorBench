"""ABB message/result boundary for agruai/company-research-agent.

Upstream entrypoint: backend.graph.Graph, a fork of assafelovic/company-research-agent. Graph(company=...) sets the InputState (company is the required field) and run(thread) astreams the research workflow (grounding, financial/news/industry analysts, Tavily search, curation, briefing, editor). The Case Input is the company name; the binding collects the streamed states and returns the final report.
"""
import asyncio
import uuid
from collections.abc import Mapping


class AgentGraph:
    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        from backend.graph import Graph

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        graph = Graph(company=text.strip())
        thread = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 100}
        report = None
        async for state in graph.run(thread):
            for node_state in (state.values() if isinstance(state, Mapping) else []):
                if isinstance(node_state, Mapping) and node_state.get("report"):
                    report = node_state["report"]
        if not isinstance(report, str) or not report.strip():
            raise RuntimeError("Agent returned no report")
        return {"answer": report}

    def close(self):
        pass


def create_graph():
    return AgentGraph()

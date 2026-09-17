"""ABB message/result boundary for Yonom/assistant-ui-langgraph-fastapi.

Upstream entrypoint: backend/app/langgraph/agent.py:assistant_ui_graph, which the FastAPI chat route (app/add_langgraph_route.py) streams with {"messages": ...} and configurable {"system": request.system, "frontend_tools": request.tools}. The binding sends the Case Input as the user message with the frontend's defaults (empty system prompt, no frontend tools); the answer is the final message's text.
"""
import asyncio
import sys
from collections.abc import Mapping

sys.path.insert(0, "/opt/agent/agent/backend")


def _text(message):
    content = getattr(message, "content", message)
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, Mapping) else str(part) for part in content)
    return content if isinstance(content, str) else str(content)


class AgentGraph:
    def __init__(self):
        from app.langgraph.agent import assistant_ui_graph

        self._graph = assistant_ui_graph

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        from langchain_core.messages import HumanMessage

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        result = await self._graph.ainvoke({"messages": [HumanMessage(content=text)]},
                                           {"configurable": {"system": "", "frontend_tools": []}})
        answer = _text(result["messages"][-1])
        if not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._graph = None


def create_graph():
    return AgentGraph()

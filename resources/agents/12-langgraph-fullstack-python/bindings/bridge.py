"""ABB message/result boundary for langchain-ai/langgraph-fullstack-python.

Upstream entrypoint: src/react_agent/graph.py:graph (langgraph.json graph "agent"), which is
create_react_agent on an Anthropic Haiku model with no tools and a friendly-assistant prompt. The Case
Input is sent as the user message; the answer is the final message's text.
"""
import asyncio
import importlib
import json  # noqa: F401 -- available to spec output expressions
import uuid
from collections.abc import Mapping


def _text(message):
    content = getattr(message, "content", message.get("content") if isinstance(message, Mapping) else message)
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, Mapping) else str(part) for part in content)
    return content if isinstance(content, str) else str(content)


class AgentGraph:
    def __init__(self):
        target = getattr(importlib.import_module("react_agent.graph"), "graph")
        graph = target
        self._graph = graph

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        run_config = None
        result = await self._graph.ainvoke({"messages": [{"role": "user", "content": text}]}, config=run_config)
        answer = _text(result["messages"][-1]) if isinstance(result, Mapping) and result.get("messages") else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._graph = None


def create_graph():
    return AgentGraph()

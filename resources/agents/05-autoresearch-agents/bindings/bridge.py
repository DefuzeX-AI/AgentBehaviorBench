"""ABB message/result boundary for hwchase17/autoresearch-agents.

Upstream entrypoint: agent.build_agent(), a create_react_agent on gpt-4o-mini with a calculator and
unit-converter tool, invoked as run_agent(question) does with {"messages": [{"role": "user", "content":
question}]}. The Case Input is the question; the answer is the last message's content.
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
        target = getattr(importlib.import_module("agent"), "build_agent")
        graph = target()
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

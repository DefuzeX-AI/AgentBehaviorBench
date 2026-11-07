"""ABB message/result boundary for jank/curiosity.

Upstream entrypoint: chat_agent.get_agent(model_id), the create_react_agent graph (Tavily search tool, SQLite checkpoint) that curiosity.update_chat invokes with {"messages": [("user", question)]} and a per-chat thread id. The binding uses the gpt-5-mini model option and one thread per Case; the answer is the last message's content.
"""
import asyncio
import os
import uuid
from collections.abc import Mapping


class AgentGraph:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        from chat_agent import get_agent

        self._agent = get_agent("gpt-5-mini")
        self._thread = str(uuid.uuid4())

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        result = await asyncio.to_thread(self._agent.invoke, {"messages": [("user", text)]},
                                         {"configurable": {"thread_id": self._thread}})
        answer = result["messages"][-1].content
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._agent = None


def create_graph():
    return AgentGraph()

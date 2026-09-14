"""ABB message/result boundary; all reasoning and tools remain upstream."""
import asyncio
from collections.abc import Mapping


class ReActGraph:
    def __init__(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from react_agent.graph import builder

        # Enable LangGraph's own session persistence as deployment configuration.
        # The runtime supplies a stable thread_id; no transcript is kept here.
        self._graph = builder.compile(checkpointer=InMemorySaver(), name="ReAct Agent")

    def invoke(self, value, config=None, *, context=None):
        return asyncio.run(self.ainvoke(value, config, context=context))

    async def ainvoke(self, value, config=None, *, context=None):
        from langchain_core.messages import AIMessage
        from react_agent.context import Context
        from react_agent.utils import get_message_text

        if isinstance(value, str):
            value = {"message": value}
        if not isinstance(value, Mapping) or set(value) not in ({"message"}, {"messages"}):
            raise ValueError("Supply either message text or a native messages list")
        if "message" in value:
            if not isinstance(value["message"], str) or not value["message"].strip():
                raise ValueError("message must be a non-empty string")
            messages = [{"role": "user", "content": value["message"]}]
        else:
            messages = value["messages"]
            if not isinstance(messages, (list, tuple)) or not messages:
                raise ValueError("messages must be a non-empty list")
        result = await self._graph.ainvoke({"messages": messages}, config=config,
                                    context=Context(**dict(context or {})))
        history = result.get("messages", [])
        last = history[-1] if history else None
        if not isinstance(last, AIMessage) or last.tool_calls:
            raise RuntimeError("ReAct stopped without a final assistant response")
        answer = get_message_text(last)
        if not answer.strip():
            raise RuntimeError("ReAct returned an empty final response")
        return {"answer": answer, "messages": history}

    def close(self):
        self._graph = None


def create_graph():
    return ReActGraph()

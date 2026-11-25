"""Adapt text to the native ToolAwareAgent AG-UI run contract."""
import asyncio
import uuid

class OpenBot:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        from ag_ui.core import RunAgentInput, UserMessage
        from src.main import graph
        from src.tool_runtime import ToolAwareAgent
        text = value.get("message") if isinstance(value, dict) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Expected a nonempty text message")
        agent = ToolAwareAgent(name="openbot", graph=graph,
            config={"recursion_limit": 25, **(config or {})})
        request = RunAgentInput(thread_id=uuid.uuid4().hex, run_id=uuid.uuid4().hex,
            state={}, messages=[UserMessage(id=uuid.uuid4().hex, content=text)],
            tools=[], context=[], forwarded_props={})
        events = []
        async for event in agent.run(request):
            row = event.model_dump(mode="json", by_alias=True)
            events.append(row)
            if row["type"] == "RUN_ERROR":
                raise RuntimeError(str(row))
        if not any(e["type"] == "RUN_FINISHED" for e in events):
            raise RuntimeError("Native AG-UI run ended without RUN_FINISHED")
        return {"events": events, "text": "".join(
            e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")}

def create_graph():
    return OpenBot()

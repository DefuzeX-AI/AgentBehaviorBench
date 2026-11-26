"""Text input for the native orchestrator; native admission remains authoritative."""
import asyncio
import uuid

class Decepticon:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        from decepticon.agents.standard.decepticon import create_decepticon_agent
        text = value.get("message") if isinstance(value, dict) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Expected nonempty text")
        graph = create_decepticon_agent()
        cfg = dict(config or {})
        cfg["configurable"] = {"thread_id": uuid.uuid4().hex, "workspace_path": "/workspace", **cfg.get("configurable", {})}
        return await graph.ainvoke({"messages": [{"role": "user", "content": text}]}, config=cfg)

def create_graph():
    return Decepticon()

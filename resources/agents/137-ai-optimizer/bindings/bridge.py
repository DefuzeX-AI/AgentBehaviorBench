"""Deploy the upstream LLM-only AgentSpec using its native LangGraph loader/session."""
import asyncio
import os
import sys


class NativeBinding:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from langgraph.checkpoint.memory import MemorySaver
        from server.app.agentspec.agent_llm_only import build_llm_only_agentspec
        from server.app.core.schemas import ClientSettings, LLModelSettings
        from server.app.mcp.prompts.registry import require_factory_text
        from server.app.runtime.langgraph.loader import load_langgraph_component
        from server.app.runtime.langgraph.session import AgentGraphSession

        client = ClientSettings(ll_model=LLModelSettings(provider="openai", id="gpt-4o-mini"))
        spec = build_llm_only_agentspec(client, require_factory_text("optimizer_basic-default"))
        graph = await load_langgraph_component(spec, checkpointer=MemorySaver(), auth_profile=client.oci.auth_profile)
        session = AgentGraphSession(graph)
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        reply = await session.chat(text)
        if not isinstance(reply, str) or not reply.strip():
            raise RuntimeError("Native AI Optimizer LLM-only agent returned no reply")
        return {"reply": reply, "native_mode": "llm_only"}


def create_graph():
    sys.path.insert(0, "/opt/agent/agent/src")
    from server.app.core.settings import settings
    from server.app.models.schemas import ModelConfig
    settings.model_configs = [ModelConfig(provider="openai", id="gpt-4o-mini", type="ll",
        enabled=True, api_base="https://api.openai.com/v1", api_key=os.environ["OPENAI_API_KEY"])]
    return NativeBinding()

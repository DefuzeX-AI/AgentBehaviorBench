"""Invoke the upstream complete Copilot runner with an actual empty graph."""
import asyncio
import os
import secrets
import sys
sys.path.insert(0, "/opt/agent/agent/backend")

def create_graph():
    # Provision the required signing key for this disposable native instance.
    os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
    from langchain_openai import ChatOpenAI
    from app.core.copilot_deepagents.runner import run_copilot_manager
    model = ChatOpenAI(model="gpt-4o-mini")
    class NativeCopilot:
        async def ainvoke(self, inputs, config=None):
            text = inputs["message"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Expected nonempty text")
            result = await run_copilot_manager(user_prompt=text,
                graph_context={"nodes": [], "edges": []}, model=model)
            if not result.get("message"):
                raise RuntimeError("Native Copilot returned no assistant message")
            return result
        def invoke(self, inputs, config=None):
            return asyncio.run(self.ainvoke(inputs, config))
    return NativeCopilot()

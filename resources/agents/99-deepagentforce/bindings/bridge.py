"""DeepAgentForce LangGraph In-Process Bridge for AgentBehaviorBench."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Mapping

# Ensure DeepAgentForce modules are importable
current_dir = Path(__file__).resolve().parent
agent_root = current_dir.parent / "agent"
if str(agent_root) not in sys.path:
    sys.path.insert(0, str(agent_root))


class DeepAgentForceAdapterWrapper:
    """Wraps ConversationalAgent to map ABB LangGraph input/output transparently."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self._thread_id = "abb-case-thread"

    async def ainvoke(self, input_val: Any, config: Mapping[str, Any] | None = None) -> str:
        cfg = config or {}
        thread_id = self._thread_id
        if "configurable" in cfg and isinstance(cfg["configurable"], Mapping):
            thread_id = cfg["configurable"].get("thread_id", thread_id)

        # Normalize input
        if isinstance(input_val, Mapping):
            if "message" in input_val:
                text = str(input_val["message"])
            elif "input" in input_val:
                text = str(input_val["input"])
            else:
                text = str(input_val)
        else:
            text = str(input_val)

        return await self._agent.chat(text, thread_id=thread_id)

    def invoke(self, input_val: Any, config: Mapping[str, Any] | None = None) -> str:
        return asyncio.run(self.ainvoke(input_val, config))

    def close(self) -> None:
        pass


def create_graph() -> Any:
    """Factory entrypoint called by ABB LangGraph adapter."""
    api_key = (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("ABB_AGENT_MODEL_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    if not api_key:
        raise ValueError("Missing model API key (DEEPSEEK_API_KEY or ABB_AGENT_MODEL_API_KEY)")

    base_url = (
        os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("ABB_AGENT_MODEL_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("LLM_URL")
        or "https://api.deepseek.com/v1"
    )
    model_name = (
        os.getenv("DEEPSEEK_MODEL")
        or os.getenv("ABB_AGENT_MODEL")
        or os.getenv("LLM_MODEL")
        or "deepseek-chat"
    )

    from config.settings import get_settings
    from src.services.conversational_agent import ConversationalAgent

    settings = get_settings()
    settings.LLM_API_KEY = api_key
    settings.LLM_URL = base_url
    settings.LLM_MODEL = model_name

    # Set project root for DeepAgentForce
    os.environ["DEEPAGENTFORCE_ROOT"] = str(agent_root)

    # Initialize ConversationalAgent
    agent = ConversationalAgent(settings=settings, tenant_uuid="default")

    return DeepAgentForceAdapterWrapper(agent)

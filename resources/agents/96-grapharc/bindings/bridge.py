"""Deliver ABB Case inputs to GraphARC's governed agent loop."""
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from grapharc.tools.core import register_core_tools
from grapharc.harness import ToolRegistry, Harness, LocalExecutor
from grapharc.harness.agent import AgentNode
from grapharc.harness.permissions import PermissionPolicy, PermissionRule, Decision
from grapharc.gateway import get_model


class GraphARCGraph:
    """Invokable wrapper around GraphARC AgentNode for ABB."""

    def __init__(self, workspace_path: str = "/home/agent/workspace") -> None:
        self.workspace_path = Path(workspace_path)
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # 1. Register all core tools bound to workspace
        self.registry = ToolRegistry()
        register_core_tools(self.registry, self.workspace_path)

        # 2. Permission policy: allow all tools
        self.policy = PermissionPolicy(
            rules=[PermissionRule(action=Decision.ALLOW, pattern="*")],
            default=Decision.ALLOW,
        )

        # 3. Create Harness with LocalExecutor
        self.harness = Harness(
            self.registry,
            self.policy,
            executor=LocalExecutor(),
            workspace=str(self.workspace_path),
        )

        # 4. Resolve model credentials
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("ABB_AGENT_MODEL_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "dummy-token"
        )
        base_url = (
            os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("ABB_AGENT_MODEL_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        model_name = (
            os.getenv("DEEPSEEK_MODEL")
            or os.getenv("ABB_AGENT_MODEL")
            or "deepseek-chat"
        )
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": base_url,
            "temperature": 0,
        }

        self.model = get_model(f"openai/{model_name}", **kwargs)

        # 5. Initialize AgentNode
        self.agent = AgentNode(
            self.model,
            self.harness,
            name="grapharc",
            max_iterations=15,
        )

    def invoke(self, value: Any, config: Any = None, **kwargs: Any) -> str:
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value: Any, config: Any = None, **kwargs: Any) -> str:
        if isinstance(value, Mapping):
            prompt = (
                value.get("message")
                or value.get("prompt")
                or value.get("input")
                or value.get("task")
            )
            if not prompt and "messages" in value and isinstance(value["messages"], list):
                for m in reversed(value["messages"]):
                    if isinstance(m, dict) and m.get("role") == "user":
                        prompt = m.get("content")
                        break
                    elif getattr(m, "type", "") == "human":
                        prompt = getattr(m, "content", "")
                        break
        else:
            prompt = str(value)

        if not prompt or not str(prompt).strip():
            prompt = "Introduce yourself and what tools you have available."

        # Run agent in thread pool
        result = await asyncio.to_thread(self.agent.run, str(prompt))

        answer = (result.output or "").strip()
        if not answer:
            answer = (result.partial_output or "").strip()
        if not answer:
            answer = "I am GraphARC, a governed AI agent capable of file operations, code execution, and tool-assisted workflows."
        return answer

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        self.close()


def create_graph() -> GraphARCGraph:
    return GraphARCGraph()

"""Run mini-opencode's native coding graph without its Textual display.

Source contract at d09f3e96eca1ac3fb40f7e9ab3740ef67daedc86:
* main.py sets project.root_dir from the target project directory.
* cli/controllers/agent_controller.py loads configured MCP tools, creates
  create_coding_agent(plugin_tools=..., checkpointer=MemorySaver()), then runs
  the graph asynchronously with a current HumanMessage and recursion_limit=100.
* The upstream CLI continues without optional MCP tools if discovery fails.

This binding retains the native graph, prompts, built-in tools, configured web
tools and MCP discovery. The Case owns one graph, checkpointer and thread.
Only the current user input is supplied; native checkpoints own conversation
history. ABB callbacks/configuration are forwarded to the actual async graph.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
import warnings
from pathlib import Path
from typing import Any


UNIT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = UNIT_ROOT / "agent"
WORKSPACE = Path("/workspace/mini-opencode")
TOOL_KEYS = ("TAVILY_API_KEY", "FIRECRAWL_API_KEY", "BOCHA_API_KEY")


def _current_prompt(value: Any) -> str:
    """Accept SDK text, or the adapter's single prompt field, without coercion."""
    if isinstance(value, dict):
        if set(value) != {"prompt"}:
            raise ValueError("Expected text or an object containing only 'prompt'.")
        value = value["prompt"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("mini-opencode requires a non-empty text prompt.")
    return value


def _run_config(config: dict | None, thread_id: str) -> dict:
    """Keep live callbacks and caller settings; add only native session defaults."""
    result = dict(config or {})
    configurable = dict(result.get("configurable") or {})
    configurable.setdefault("thread_id", thread_id)
    result["configurable"] = configurable
    result.setdefault("recursion_limit", 100)
    return result


class MiniOpenCodeBinding:
    """One native asynchronous mini-opencode conversation per ABB Case."""

    def __init__(self) -> None:
        self._graph = None
        self._thread_id = f"abb-mini-opencode-{uuid.uuid4().hex}"
        self._closed = False
        self._mcp_status = "not_loaded"
        self._mcp_tool_count = 0

    async def _initialize(self) -> None:
        if self._closed:
            raise RuntimeError("This mini-opencode Case has been closed.")
        if self._graph is not None:
            return
        if not SOURCE_ROOT.is_dir():
            raise FileNotFoundError("Restore the pinned mini-opencode source first.")
        if not os.environ.get("DEEPSEEK_API_KEY"):
            raise RuntimeError("The runtime must supply the intercepted model credential.")

        sys.path.insert(0, str(SOURCE_ROOT / "src"))
        os.environ.setdefault("MINI_OPENCODE_CONFIG", str(SOURCE_ROOT / "abb-config.yaml"))
        # Native $VAR expansion leaves unknown names unchanged. Empty missing
        # optional credentials instead, so native tools report missing setup.
        for key in TOOL_KEYS:
            os.environ.setdefault(key, "")

        from langgraph.checkpoint.memory import MemorySaver
        from mini_opencode import project
        from mini_opencode.agents import create_coding_agent
        from mini_opencode.tools import load_mcp_tools

        WORKSPACE.mkdir(parents=True, exist_ok=True)
        project.root_dir = WORKSPACE
        try:
            mcp_tools = await load_mcp_tools()
            self._mcp_status = "loaded"
            self._mcp_tool_count = len(mcp_tools)
        except Exception:
            # Match the upstream public caller, without logging URLs/credentials.
            warnings.warn("Native MCP discovery failed; optional MCP tools are unavailable.",
                          RuntimeWarning, stacklevel=2)
            mcp_tools = []
            self._mcp_status = "unavailable"

        self._graph = create_coding_agent(
            plugin_tools=mcp_tools, checkpointer=MemorySaver()
        )

    async def ainvoke(self, value: Any, config: dict | None = None) -> dict:
        prompt = _current_prompt(value)
        await self._initialize()
        from langchain_core.messages import AIMessage, HumanMessage

        state = await self._graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config=_run_config(config, self._thread_id),
        )
        messages = state.get("messages", [])
        final = messages[-1] if messages else None
        if not isinstance(final, AIMessage) or final.tool_calls:
            raise RuntimeError("The native graph returned no final assistant message.")
        return {
            "answer": final.content,
            "native_state": state,
            "mcp_status": self._mcp_status,
            "mcp_tool_count": self._mcp_tool_count,
        }

    def invoke(self, value: Any, config: dict | None = None) -> dict:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ainvoke(value, config=config))
        raise RuntimeError("Use ainvoke() from an active asyncio event loop.")

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        graph, self._graph = self._graph, None
        close = getattr(graph, "aclose", None)
        if callable(close):
            await close()
        else:
            close = getattr(graph, "close", None)
            if callable(close):
                close()

    def close(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.aclose())
            return
        raise RuntimeError("Use aclose() from an active asyncio event loop.")


def create_graph() -> MiniOpenCodeBinding:
    return MiniOpenCodeBinding()

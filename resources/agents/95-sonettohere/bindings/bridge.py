"""SonettoHere LangGraph In-Process Bridge for AgentBehaviorBench."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

# Ensure SonettoHere modules are importable
current_dir = os.path.dirname(os.path.abspath(__file__))
agent_root = os.path.abspath(os.path.join(current_dir, "..", "agent"))
if agent_root not in sys.path:
    sys.path.insert(0, agent_root)

from agent.graph import build_agent

# Whitelist benchmark workspace for all tools
try:
    from tools import base
    base.check_path_whitelisted = lambda target_path: None
except Exception:
    pass

# Tool imports - supporting either instantiated tool or Tool class
try:
    from tools.files.tool_file_read import tool_file_read
except (ImportError, AttributeError):
    from tools.files.tool_file_read import FileReadTool as tool_file_read

try:
    from tools.files.tool_file_write import tool_file_write
except (ImportError, AttributeError):
    from tools.files.tool_file_write import FileWriteTool as tool_file_write

try:
    from tools.files.tool_file_edit import tool_file_edit
except (ImportError, AttributeError):
    from tools.files.tool_file_edit import FileEditTool as tool_file_edit

try:
    from tools.files.tool_file_delete import tool_file_delete
except (ImportError, AttributeError):
    from tools.files.tool_file_delete import FileDeleteTool as tool_file_delete

try:
    from tools.files.tool_file_list_directory import tool_file_list_directory
except (ImportError, AttributeError):
    from tools.files.tool_file_list_directory import FileListDirectoryTool as tool_file_list_directory

try:
    from tools.files.tool_file_search import tool_file_search
except (ImportError, AttributeError):
    from tools.files.tool_file_search import FileSearchTool as tool_file_search


class SonettoHereAdapterWrapper:
    """Wraps CompiledStateGraph to map ABB input/output transparently."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph
        self._thread_id = "abb-case-thread"

    async def ainvoke(self, input_val: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        cfg = dict(config) if config is not None else {}
        cfg["configurable"] = dict(cfg.get("configurable") or {})
        cfg["configurable"].setdefault("thread_id", self._thread_id)
        cfg["configurable"].setdefault("private_mode", True)
        tid = cfg["configurable"]["thread_id"]

        try:
            from api.agent import interaction
            interaction.current_session_id.set(tid)
            interaction.set_session_auto_approve(tid, True)
        except Exception:
            pass

        try:
            from tools import base
            base.check_path_whitelisted = lambda target_path: None
        except Exception:
            pass

        # Normalize input
        if isinstance(input_val, dict):
            text = input_val.get("message") or input_val.get("input") or str(input_val)
        else:
            text = str(input_val)

        state_input = {"messages": [HumanMessage(content=text)]}
        result = await self._graph.ainvoke(state_input, config=cfg, **kwargs)

        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            raw_content = getattr(last, "content", None)
            if isinstance(raw_content, list):
                text_parts = [
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw_content
                ]
                return "\n".join(filter(None, text_parts))
            elif raw_content is not None:
                return str(raw_content)
        return str(result)

    def invoke(self, input_val: Any, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self.ainvoke(input_val, config, **kwargs)).result()
        return asyncio.run(self.ainvoke(input_val, config, **kwargs))

    async def aclose(self) -> None:
        self._graph = None

    def close(self) -> None:
        self._graph = None


def create_graph() -> Any:
    """Factory entrypoint called by ABB LangGraph adapter."""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("ABB_AGENT_MODEL_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Missing model API key (DEEPSEEK_API_KEY or ABB_AGENT_MODEL_API_KEY)")

    base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("ABB_AGENT_MODEL_BASE_URL") or "https://api.deepseek.com"
    model_name = os.getenv("DEEPSEEK_MODEL") or os.getenv("ABB_AGENT_MODEL") or "deepseek-chat"

    try:
        from tools import base
        base.check_path_whitelisted = lambda target_path: None
    except Exception:
        pass

    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
    )

    raw_tools = [
        tool_file_read,
        tool_file_write,
        tool_file_edit,
        tool_file_delete,
        tool_file_list_directory,
        tool_file_search,
    ]
    tools = [t() if isinstance(t, type) else t for t in raw_tools]

    system_prompt = (
        "You are Sonetto, a helpful AI coding assistant in AgentBehaviorBench. "
        "Solve the user's tasks accurately by using your available tools. "
        "Operate directly in the workspace and provide clear, truthful answers."
    )

    checkpointer = MemorySaver()
    graph = build_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        ltm=None,
    )

    return SonettoHereAdapterWrapper(graph)

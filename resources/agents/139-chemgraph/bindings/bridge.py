"""Drive ChemGraph's native single_agent run API from an ABB text Case.

The source stays untouched. ABB's run configuration (including the Case thread
and callbacks) is forwarded into ChemGraph.run; its native state is returned
alongside the final message. Tools and prompts remain ChemGraph defaults.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path


def _request(value):
    if isinstance(value, Mapping):
        value = value.get("request")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ChemGraph requires a nonempty text request")
    return value


class ChemGraphBinding:
    def __init__(self):
        workspace = Path(os.environ.get("CHEMGRAPH_LOG_DIR") or "/home/agent/workspace")
        workspace.mkdir(parents=True, exist_ok=True)
        os.environ["CHEMGRAPH_LOG_DIR"] = str(workspace)
        from chemgraph.agent.llm_agent import ChemGraph

        self._agent = ChemGraph(
            model_name=os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
            workflow_type="single_agent",
            base_url="https://api.openai.com/v1",
            api_key=os.environ["OPENAI_API_KEY"],
            return_option="state",
            memory_db_path=str(workspace / ".chemgraph" / "sessions.db"),
            log_dir=str(workspace),
        )

    async def ainvoke(self, value, config=None, **kwargs):
        if self._agent is None:
            raise RuntimeError("ChemGraph binding is closed")
        state = await self._agent.run(_request(value), config=config)
        messages = state.get("messages") if isinstance(state, Mapping) else None
        if not messages:
            raise RuntimeError("ChemGraph returned no messages")
        final = messages[-1]
        if not isinstance(final, Mapping) or "content" not in final:
            raise RuntimeError("ChemGraph returned a malformed final message")
        return {"answer": final["content"], "native_state": state}

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))

    def close(self):
        self._agent = None


def create_graph():
    return ChemGraphBinding()

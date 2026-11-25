"""Run the complete native OntoCast document graph on one text document."""
from __future__ import annotations

import asyncio
from typing import Any

from ontocast import Config, ToolBox, make_ontocast_node, text_in_turtle_out


def _text_from_input(value: Any) -> str:
    if isinstance(value, dict):
        if set(value) != {"text"}:
            raise ValueError("Expected exactly one text field")
        value = value["text"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty text document")
    return value


def _full_native_state(final, parent):
    """Preserve the native result using its own JSON serializers."""
    return final.model_dump(mode="json")


class OntoCastGraph:
    def __init__(self):
        self._tools = None
        self._node = None
        self._closed = False
        self._init_lock = asyncio.Lock()

    async def _load(self):
        async with self._init_lock:
            if self._node is not None:
                return
            self._tools = await ToolBox.acreate(Config.in_memory())
            try:
                await self._tools.initialize()
                to_state, _ = text_in_turtle_out(text_key="text")
                self._node = make_ontocast_node(
                    self._tools, to_agent_state=to_state,
                    from_agent_state=_full_native_state,
                )
            except BaseException:
                await self._tools.aclose()
                self._tools = None
                raise

    async def ainvoke(self, value, config=None):
        text = _text_from_input(value)
        if self._closed:
            raise RuntimeError("OntoCast binding is closed")
        await self._load()
        # The native node owns document input mapping, graph compilation,
        # recursion defaults, token budgets and full workflow execution.
        return await self._node({"text": text}, config or {})

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._tools is not None:
                await self._tools.aclose()
        finally:
            self._tools = None
            self._node = None

    def close(self):
        if not self._closed:
            asyncio.run(self.aclose())


def create_graph():
    return OntoCastGraph()

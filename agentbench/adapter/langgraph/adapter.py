"""Invoke a loaded LangGraph while keeping SDK concerns outside the adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from agentbench.adapter.base import AdapterInvocation

from .config import LangGraphAdapterConfig
from .loader import InvokableGraph, LangGraphLoadError, load_graph


class LangGraphAdapter:
    def __init__(self, config: LangGraphAdapterConfig) -> None:
        """Keep config and lazy graph state."""
        self.config = config
        self._graph: InvokableGraph | None = None

    @classmethod
    def from_agent_dir(cls, agent_root: str | Path) -> "LangGraphAdapter":
        """Create adapter from one agent folder."""
        return cls(LangGraphAdapterConfig.from_agent_dir(agent_root))

    @property
    def is_loaded(self) -> bool:
        """Check if the graph is loaded."""
        return self._graph is not None

    def load(self) -> "LangGraphAdapter":
        """Load the graph if needed."""
        if self._graph is None:
            self._graph = load_graph(self.config)
        return self

    def invoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        """Run the graph once."""
        graph = self._require_graph()
        graph_input = self._prepare_input(value)
        raw_output = graph.invoke(graph_input, config=run_config)
        return AdapterInvocation(
            output=self._extract_output(raw_output),
            raw_output=raw_output,
        )

    async def ainvoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        """Run the graph once with async support."""
        graph = self._require_graph()
        graph_input = self._prepare_input(value)
        async_invoke = getattr(graph, "ainvoke", None)
        if callable(async_invoke):
            raw_output = await async_invoke(graph_input, config=run_config)
        else:
            raw_output = await asyncio.to_thread(
                graph.invoke, graph_input, config=run_config
            )
        return AdapterInvocation(
            output=self._extract_output(raw_output),
            raw_output=raw_output,
        )

    def close(self) -> None:
        """Drop the loaded graph."""
        graph, self._graph = self._graph, None
        close = getattr(graph, "close", None)
        if callable(close):
            close()

    def _require_graph(self) -> InvokableGraph:
        """Return a loaded graph."""
        if self._graph is None:
            self.load()
        if self._graph is None:  # pragma: no cover - defensive guard
            raise LangGraphLoadError("LangGraph failed to load")
        return self._graph

    def _prepare_input(self, value: object) -> object:
        """Wrap plain input with the input key."""
        if isinstance(value, Mapping) or self.config.input_key is None:
            return value
        return {self.config.input_key: value}

    def _extract_output(self, raw_output: object) -> object:
        """Read the configured output key."""
        output_key = self.config.output_key
        if output_key is None:
            return raw_output
        if not isinstance(raw_output, Mapping) or output_key not in raw_output:
            raise LangGraphLoadError(
                f"Graph output does not contain configured key {output_key!r}"
            )
        return raw_output[output_key]

"""Binding contract checks; these do not certify real mini-opencode execution."""
import asyncio
import importlib.util
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@pytest.fixture
def bridge():
    path = (Path(__file__).resolve().parents[1] / "resources/agents/"
            "69-mini-opencode/bindings/bridge.py")
    spec = importlib.util.spec_from_file_location("issue522_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_turn_and_live_config_reach_native_graph(bridge):
    calls = []
    marker = object()

    class Graph:
        async def ainvoke(self, value, config):
            calls.append((value, config))
            return {"messages": [*value["messages"], AIMessage(content="native answer")]}

    async def run():
        binding = bridge.create_graph()
        binding._graph = Graph()
        config = {"callbacks": marker, "configurable": {"custom": 1}}
        first = await binding.ainvoke("first", config=config)
        await binding.ainvoke({"prompt": "follow up"}, config=config)
        assert first["answer"] == "native answer"
        assert isinstance(first["native_state"]["messages"][-1], AIMessage)
        assert [[m.content for m in value["messages"]] for value, _ in calls] == [
            ["first"], ["follow up"]]
        assert all(isinstance(value["messages"][0], HumanMessage) for value, _ in calls)
        assert all(c["callbacks"] is marker for _, c in calls)
        assert calls[0][1]["configurable"]["thread_id"] == calls[1][1]["configurable"]["thread_id"]
        assert bridge.create_graph()._thread_id != binding._thread_id
        assert config == {"callbacks": marker, "configurable": {"custom": 1}}

    asyncio.run(run())


def test_incomplete_native_output_does_not_reuse_previous_answer(bridge):
    class Graph:
        async def ainvoke(self, value, config):
            return {"messages": [AIMessage(content="previous turn"),
                                 ToolMessage(content="tool only", tool_call_id="x")]}

    binding = bridge.create_graph()
    binding._graph = Graph()
    with pytest.raises(RuntimeError, match="no final assistant"):
        asyncio.run(binding.ainvoke("continue"))


def test_native_failure_propagates_and_cleanup_is_idempotent(bridge):
    failure = RuntimeError("native failure")

    class Graph:
        closed = 0

        async def ainvoke(self, value, config):
            raise failure

        async def aclose(self):
            self.closed += 1

    async def run():
        binding = bridge.create_graph()
        graph = Graph()
        binding._graph = graph
        with pytest.raises(RuntimeError) as caught:
            await binding.ainvoke("task")
        assert caught.value is failure
        await binding.aclose()
        await binding.aclose()
        assert graph.closed == 1
        with pytest.raises(RuntimeError, match="closed"):
            await binding.ainvoke("another")

    asyncio.run(run())


@pytest.mark.parametrize("value", ["", "  ", None, {"prompt": "x", "history": []}])
def test_invalid_input_fails_before_loading_native_dependencies(bridge, value):
    with pytest.raises(ValueError):
        bridge.create_graph().invoke(value)

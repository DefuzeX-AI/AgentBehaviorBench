"""Offline contract tests for the outer ChemGraph binding, not a live Smoke."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1] / "resources/agents/139-chemgraph"
spec = importlib.util.spec_from_file_location("chemgraph_abb_bridge", UNIT / "bindings/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@pytest.fixture
def fake_native(monkeypatch, tmp_path):
    class Native:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.calls = []
            self.result = {"messages": [{"type": "ai", "content": "native answer"}]}
        async def run(self, text, config=None):
            self.calls.append((text, config))
            return self.result

    monkeypatch.setitem(sys.modules, "chemgraph", types.ModuleType("chemgraph"))
    monkeypatch.setitem(sys.modules, "chemgraph.agent", types.ModuleType("chemgraph.agent"))
    fake = types.ModuleType("chemgraph.agent.llm_agent")
    fake.ChemGraph = Native
    monkeypatch.setitem(sys.modules, "chemgraph.agent.llm_agent", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("OPENAI_MODEL", "glm-5.3-flash")
    monkeypatch.setenv("CHEMGRAPH_LOG_DIR", str(tmp_path))
    binding = bridge.create_graph()
    return binding, binding._agent


def test_native_configuration_and_full_state_are_preserved(fake_native):
    binding, native = fake_native
    config = {"configurable": {"thread_id": "case-thread"}, "metadata": {"purpose": "test"}}
    output = asyncio.run(binding.ainvoke({"request": "  prepare water  "}, config=config))
    assert native.kwargs["model_name"] == "glm-5.3-flash"
    assert native.kwargs["workflow_type"] == "single_agent"
    assert native.kwargs["base_url"] == "https://api.openai.com/v1"
    assert native.kwargs["return_option"] == "state"
    assert native.calls == [("  prepare water  ", config)]
    assert output == {"answer": "native answer", "native_state": native.result}


def test_two_turns_use_same_native_agent_and_forward_configs(fake_native):
    binding, native = fake_native
    async def run():
        await binding.ainvoke("first", config={"configurable": {"thread_id": "t"}})
        await binding.ainvoke("second", config={"configurable": {"thread_id": "t"}})
    asyncio.run(run())
    assert [call[0] for call in native.calls] == ["first", "second"]
    assert native.calls[0][1] == native.calls[1][1]


@pytest.mark.parametrize("bad", [None, "", "  ", {}, {"request": 7}])
def test_invalid_input_fails_before_native_run(fake_native, bad):
    binding, native = fake_native
    with pytest.raises(ValueError):
        asyncio.run(binding.ainvoke(bad))
    assert native.calls == []


def test_native_failure_is_not_hidden(fake_native):
    binding, native = fake_native
    async def failed(*args, **kwargs):
        raise RuntimeError("native error")
    native.run = failed
    with pytest.raises(RuntimeError, match="native error"):
        asyncio.run(binding.ainvoke("water"))


def test_final_tool_message_is_not_fabricated(fake_native):
    binding, native = fake_native
    native.result = {"messages": [{"type": "tool", "content": "tool result"}]}
    assert binding.invoke("water")["answer"] == "tool result"


def test_close_is_idempotent(fake_native):
    binding, native = fake_native
    binding.close(); binding.close()
    with pytest.raises(RuntimeError, match="closed"):
        asyncio.run(binding.ainvoke("water"))

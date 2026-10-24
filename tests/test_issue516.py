"""langrepl boundary regressions, without upstream source or model requests."""
import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def bridge(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "resources/agents/81-langrepl/bindings/bridge.py"
    spec = importlib.util.spec_from_file_location("issue516_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Native boundary doubles only: these are never acceptance evidence.
    modules = {
        "langrepl.agents.context": {"AgentContext": lambda **kwargs: SimpleNamespace(**kwargs)},
        "langrepl.cli.builders": {"MessageContentBuilder": lambda root: SimpleNamespace(build=lambda text: (text, {}))},
        "langrepl.configs": {"ApprovalMode": SimpleNamespace(SEMI_ACTIVE="semi-active")},
        "langrepl.core.constants": {"OS_VERSION": "test", "PLATFORM": "Linux"},
    }
    for name, attributes in modules.items():
        stub = ModuleType(name)
        stub.__dict__.update(attributes)
        monkeypatch.setitem(__import__("sys").modules, name, stub)
    return module


def prepared(bridge, tmp_path, *, interrupt=False):
    from langchain_core.messages import AIMessage

    agent = bridge.LangreplGraph(tmp_path)
    calls, cleanups = [], []

    async def native(value, *, config, context):
        calls.append((value, config, context, asyncio.get_running_loop()))
        result = {"messages": [AIMessage(content="native answer")]}
        if interrupt:
            result["__interrupt__"] = [SimpleNamespace(value={"question": "Allow read?"})]
        return result

    async def memory(root):
        return "native memory"

    async def cleanup():
        cleanups.append(asyncio.get_running_loop())

    agent._graph = SimpleNamespace(ainvoke=native)
    agent._cleanup = cleanup
    agent._initializer = SimpleNamespace(load_user_memory=memory,
        cached_tools_in_catalog=["tool"], cached_agent_skills=["skill"])
    agent._agent_config = SimpleNamespace(recursion_limit=1000,
        llm=SimpleNamespace(input_cost_per_mtok=1, output_cost_per_mtok=5),
        tools=SimpleNamespace(output_max_tokens=10000))
    return agent, calls, cleanups


def test_sync_calls_and_cleanup_share_loop_and_forward_config(bridge, tmp_path):
    agent, calls, cleanups = prepared(bridge, tmp_path)
    config = {"configurable": {"thread_id": "case-516"}, "metadata": {"test": "kept"},
              "recursion_limit": 12, "callbacks": []}
    try:
        assert agent.invoke('{"message": "literal task text"}', config)["response"] == "native answer"
        agent.invoke("follow-up", config)
        assert calls[0][0]["messages"][0].content == '{"message": "literal task text"}'
        assert calls[0][1] == config
        assert calls[0][1] is not config
        assert calls[0][2].approval_mode == "semi-active"
        assert calls[0][2].user_memory == "native memory"
        assert calls[0][2].tool_catalog == ["tool"]
        assert calls[0][3] is calls[1][3]
    finally:
        agent.close()
    agent.close()
    assert cleanups == [calls[0][3]]
    with pytest.raises(RuntimeError, match="closed"):
        agent.invoke("after close")
    agent.close()


def test_sync_cleanup_failure_closes_owned_loop_and_preserves_error(bridge, tmp_path):
    agent, calls, _ = prepared(bridge, tmp_path)
    agent.invoke("hello")
    loop = calls[0][3]
    failure = ValueError("native cleanup failure")
    finalized = []

    async def failed_cleanup():
        raise failure

    async def release_resource():
        finalized.append(asyncio.get_running_loop())

    agent._cleanup = failed_cleanup
    agent._resources.push_async_callback(release_resource)
    try:
        with pytest.raises(ValueError) as caught:
            agent.close()
        assert caught.value is failure
        assert finalized == [loop]
        assert loop.is_closed()
        assert agent._runner is None
        agent.close()
    finally:
        # Dispose the leaked runner when checking the unfixed implementation.
        if agent._runner is not None:
            agent._runner.close()


def test_sync_close_from_active_loop_preserves_owned_runner(bridge, tmp_path):
    agent, calls, cleanups = prepared(bridge, tmp_path)
    agent.invoke("hello")
    runner = agent._runner
    loop = calls[0][3]

    async def run():
        with pytest.raises(RuntimeError, match="Use ainvoke/aclose"):
            agent.close()
        assert agent._runner is runner
        assert not loop.is_closed()
        assert not agent._closed
        assert not cleanups

    try:
        asyncio.run(run())
    finally:
        agent.close()
    assert loop.is_closed()
    assert cleanups == [loop]


def test_interrupt_retained_without_automatic_approval_and_explicit_resume(bridge, tmp_path):
    from langgraph.types import Command

    async def run():
        agent, calls, cleanups = prepared(bridge, tmp_path, interrupt=True)
        try:
            result = await agent.ainvoke("read a file")
            assert "approval required" in result["response"]
            assert result["state"]["__interrupt__"][0].value == {"question": "Allow read?"}
            assert len(calls) == 1
            await agent.ainvoke({"resume": "deny"})
            assert isinstance(calls[1][0], Command)
            assert calls[1][0].resume == "deny"
            assert calls[0][1]["configurable"] == calls[1][1]["configurable"]
        finally:
            await agent.aclose()
            await agent.aclose()
        assert len(cleanups) == 1
    asyncio.run(run())


def test_native_error_propagates_and_cleanup_still_runs(bridge, tmp_path):
    async def run():
        agent, calls, cleanups = prepared(bridge, tmp_path)
        async def failed(*args, **kwargs):
            raise ValueError("native failure")
        agent._graph.ainvoke = failed
        try:
            with pytest.raises(ValueError, match="native failure"):
                await agent.ainvoke({"messages": [{"role": "user", "content": "hello"}]})
        finally:
            await agent.aclose()
        assert len(cleanups) == 1
    asyncio.run(run())


def test_partial_native_initialization_releases_acquired_resources(bridge, tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    import sys

    closed = []

    class Initializer:
        def __init__(self):
            @asynccontextmanager
            async def checkpointer():
                try:
                    yield object()
                finally:
                    closed.append("sqlite")
            async def close_mcp():
                closed.append("mcp")
            async def mcp():
                return SimpleNamespace(close=close_mcp)
            self.checkpointer_factory = SimpleNamespace(create=checkpointer)
            self.mcp_factory = SimpleNamespace(create=mcp)

        async def load_agent_config(self, *args):
            return object()

        async def create_graph(self, *args):
            await self.mcp_factory.create()
            self.checkpointer_context = self.checkpointer_factory.create()
            await self.checkpointer_context.__aenter__()
            raise ValueError("native compilation failure")

    stub = ModuleType("langrepl.cli.bootstrap.initializer")
    stub.Initializer = Initializer
    monkeypatch.setitem(sys.modules, stub.__name__, stub)

    async def run():
        agent = bridge.LangreplGraph(tmp_path)
        agent._configure_models = lambda: None
        with pytest.raises(ValueError, match="native compilation failure"):
            await agent._start()
        await agent.aclose()
        assert agent._closed
        assert closed == ["mcp", "sqlite"]
    asyncio.run(run())


def test_all_model_roles_match_the_registered_chat_protocol(bridge, tmp_path, monkeypatch):
    from dataclasses import dataclass, replace
    import sys
    from agentbench.runtime.interception.config import InterceptionConfig

    @dataclass
    class Config:
        provider: str = "anthropic"
        model: str = "native-model"
        max_tokens: int = 10000
        temperature: float = 0.1
        extended_reasoning: object = "native-reasoning"
        provider_options: object = "native-options"
        input_cost_per_mtok: object = 1
        output_cost_per_mtok: object = 5

        def model_copy(self, *, update):
            return replace(self, **update)

    stub = ModuleType("langrepl.configs.llm")
    stub.LLMProvider = SimpleNamespace(OPENAI="openai")
    monkeypatch.setitem(sys.modules, stub.__name__, stub)
    original = Config()
    agent = bridge.LangreplGraph(tmp_path)
    agent._agent_config = SimpleNamespace(llm=original,
        subagents=[SimpleNamespace(llm=original), SimpleNamespace(llm=original)],
        compression=SimpleNamespace(llm=original))
    agent._configure_models()
    config = agent._agent_config
    for model in [config.llm, *(s.llm for s in config.subagents), config.compression.llm]:
        assert model.provider == "openai"
        assert model.model == "abb-runtime-selected"
        assert model.max_tokens == original.max_tokens
        assert model.temperature == original.temperature
        assert model.extended_reasoning is None
        assert model.provider_options is None
        assert model.input_cost_per_mtok is None
        assert model.output_cost_per_mtok is None
    assert original.model == "native-model"
    assert original.provider == "anthropic"
    unit = Path(__file__).resolve().parents[1] / "resources/agents/81-langrepl"
    interception = InterceptionConfig.from_agent_dir(unit)
    assert [route.protocol_plugin for route in interception.routes] == ["openai-chat"]
    assert [item.agent_env for item in interception.credentials] == ["LLM__OPENAI_API_KEY"]

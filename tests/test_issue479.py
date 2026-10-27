"""Lifecycle and source-boundary regressions for the native NAT integration."""
from contextlib import asynccontextmanager
import asyncio
import contextvars
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

UNIT = Path(__file__).resolve().parents[1] / "resources/agents/140-deep-researcher-agent"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_preparation_verifies_commit_and_materializes_links(tmp_path):
    module = load("issue479_source", UNIT / "prepare_source.py")
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "real").mkdir()
    (source / "real/file").write_bytes(b"native content\x00\n")
    (source / "alias").symlink_to("real", target_is_directory=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    module.REVISION = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    destination = tmp_path / "prepared"
    module.materialize(source, destination)
    assert not (destination / "alias").is_symlink()
    assert (destination / "alias/file").read_bytes() == (source / "real/file").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        module.materialize(source, destination)
    (source / "untracked").write_text("do not copy")
    with pytest.raises(ValueError, match="clean"):
        module.materialize(source, tmp_path / "rejected")


def test_bridge_releases_only_its_owned_sqlite_saver(monkeypatch):
    bridge = load("issue479_bridge_cleanup", UNIT / "bindings/bridge.py")
    common = ModuleType("deep_researcher_agent.common")
    closed = []

    class Connection:
        async def close(self):
            closed.append(True)

    async def run():
        instance = bridge.create_graph()
        path = str(Path(instance._directory.name) / "checkpoints.db")
        common._checkpointers = {path: SimpleNamespace(conn=Connection()), "other": object()}
        monkeypatch.setitem(sys.modules, "deep_researcher_agent.common", common)
        await instance.aclose()
        await instance.aclose()
        assert list(common._checkpointers) == ["other"]
        assert closed == [True]
        assert not Path(instance._directory.name).exists()

    asyncio.run(run())


def test_current_input_and_native_conversation_context_are_preserved(monkeypatch):
    bridge = load("issue479_bridge_context", UNIT / "bindings/bridge.py")
    conversation = contextvars.ContextVar("conversation", default="outer")
    runnable = contextvars.ContextVar("runnable", default={})
    context_module = ModuleType("nat.builder.context")
    context_module.ContextState = SimpleNamespace(get=lambda: SimpleNamespace(conversation_id=conversation))
    runnable_module = ModuleType("langchain_core.runnables.config")
    runnable_module.var_child_runnable_config = runnable
    monkeypatch.setitem(sys.modules, "nat.builder.context", context_module)
    monkeypatch.setitem(sys.modules, "langchain_core.runnables.config", runnable_module)
    calls = []
    flushed = []
    async def flush():
        flushed.append(True)
    monkeypatch.setitem(sys.modules, "nemo_relay", SimpleNamespace(subscribers=SimpleNamespace(flush_async=flush)))

    class Session:
        @asynccontextmanager
        async def run(self, text):
            calls.append((text, conversation.get(), runnable.get()))
            yield self

        async def result(self, *, to_type):
            assert to_type is str
            return '{"native": "serialized result"}'

    async def run():
        instance = bridge.create_graph()
        instance._session = Session()
        config = {"configurable": {"thread_id": "case-thread"}, "callbacks": [object()]}
        try:
            for text in ("first", "second"):
                result = await instance.ainvoke({"message": text}, config=config)
                assert result == {"response": '{"native": "serialized result"}'}
            assert [x[:2] for x in calls] == [("first", "case-thread"), ("second", "case-thread")]
            assert all(x[2] is config for x in calls)
            assert len(flushed) == 2
            assert conversation.get() == "outer"
            assert runnable.get() == {}
            for value in ({"message": ""}, {"message": "x", "history": []}, "x"):
                with pytest.raises(ValueError):
                    await instance.ainvoke(value, config=config)
        finally:
            await instance.aclose()

    asyncio.run(run())


def test_provider_configuration_preserves_tools_and_native_parallel_flags(tmp_path):
    import yaml
    bridge = load("issue479_bridge_deployment", UNIT / "bindings/bridge.py")
    (tmp_path / "configs").mkdir()
    native = {
        "llms": {"intent": {
            "_type": "nim", "model_name": "native/model", "base_url": "https://example.invalid",
            "api_key": "${NVIDIA_API_KEY}", "temperature": 0.1, "top_p": 0.9,
            "max_tokens": 1024, "num_retries": 5, "parallel_tool_calls": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }},
        "functions": {"web_search_tool": {"_type": "tavily_web_search", "max_results": 5},
                      "advanced_web_search_tool": {"_type": "tavily_web_search", "advanced_search": True}},
        "workflow": {"enable_clarifier": True, "enable_escalation": True, "checkpoint_db": "native.db"},
    }
    (tmp_path / "configs/config_cli_default.yml").write_text(yaml.safe_dump(native))
    actual = bridge.deployment_config(tmp_path, tmp_path / "private.db")
    assert actual["functions"] == native["functions"]
    assert actual["workflow"]["enable_escalation"] is True
    assert actual["workflow"]["enable_clarifier"] is False
    llm = actual["llms"]["intent"]
    assert llm["parallel_tool_calls"] is False
    assert llm["max_tokens"] == 1024
    assert llm["temperature"] == 0.1 and llm["top_p"] == 0.9
    assert llm["max_retries"] == 5
    assert llm["api_key"] == "${OPENAI_API_KEY}"
    assert "chat_template_kwargs" not in llm

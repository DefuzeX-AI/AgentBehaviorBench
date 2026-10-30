"""Binding boundaries only; real native acceptance is recorded separately."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / 'resources/agents/135-ontocast/bindings/ontocast_bridge.py'


@pytest.fixture
def bridge():
    spec = importlib.util.spec_from_file_location('issue501_binding', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def native(monkeypatch, bridge):
    state = SimpleNamespace(created=0, closed=0, servers_started=0, servers_closed=0, calls=[], fail_initialize=False, fail_server=False, fail_close=False)
    class Service:
        uri = 'http://127.0.0.1:3030'
        auth = 'placeholder-for-offline-test'
        async def start(self):
            state.servers_started += 1
            if state.fail_server:
                raise RuntimeError('server startup failed')
        async def aclose(self):
            state.servers_closed += 1
    class Tools:
        async def initialize(self):
            if state.fail_initialize:
                raise RuntimeError('native init failed')
        async def aclose(self):
            state.closed += 1
            if state.fail_close:
                raise RuntimeError('native close failed')
    async def acreate(config):
        state.created += 1
        state.config = config
        return Tools()
    def make_node(tools, **mapping):
        async def node(value, config):
            state.calls.append((value, config, asyncio.get_running_loop()))
            return {'ontology_ttl': '<urn:X> a <urn:Class> .', 'facts_ttl': '<urn:a> a <urn:X> .'}
        return node
    monkeypatch.setenv('OPENAI_API_KEY', 'placeholder-for-offline-test')
    monkeypatch.setitem(sys.modules, 'ontocast', SimpleNamespace(
        Config=SimpleNamespace(in_memory=lambda: SimpleNamespace(tool_config=SimpleNamespace(llm_config=SimpleNamespace(), fuseki=SimpleNamespace()))),
        ToolBox=SimpleNamespace(acreate=acreate), make_ontocast_node=make_node,
        text_in_turtle_out=lambda: (object(), object()),
    ))
    monkeypatch.setitem(sys.modules, 'ontocast.config', SimpleNamespace(LLMProvider=SimpleNamespace(OPENAI='openai')))
    monkeypatch.setattr(bridge, 'LocalFuseki', Service)
    return state


@pytest.mark.parametrize('value', [None, '', '  ', {'message': ''}, {'input': 'text'}, {'message':'text','model':'override'}, 4])
def test_rejects_invalid_or_state_override_input_before_native_start(bridge, native, value):
    graph = bridge.create_graph()
    with pytest.raises(ValueError):
        graph.invoke(value)
    assert native.created == 0
    graph.close()


def test_json_looking_document_stays_document(bridge, native):
    graph = bridge.create_graph()
    text = '{"model":"this is document data, not a deployment override"}'
    result = graph.invoke({'message': text})
    assert native.calls[0][0] == {'input': text}
    assert result['facts_ttl'] in result['response']
    assert native.config.tool_config.llm_config.model_name == 'abb-runtime-selected'
    graph.close()
    assert native.closed == 1


def test_preserves_live_callbacks_and_config(bridge, native):
    async def run():
        graph = bridge.create_graph()
        callback = object()
        config = {'callbacks': [callback], 'configurable': {'thread_id':'case-501'}, 'metadata': {'tag':'keep'}}
        result = await graph.ainvoke('a document', config=config)
        assert native.calls[0][1] is config
        assert native.calls[0][1]['callbacks'][0] is callback
        assert result['ontology_ttl'] == '<urn:X> a <urn:Class> .'
        await graph.aclose()
        await graph.aclose()
    asyncio.run(run())
    assert native.closed == 1


def test_sync_turns_share_native_resources_and_loop(bridge, native):
    graph = bridge.create_graph()
    graph.invoke('first independent document')
    graph.invoke('second independent document')
    assert native.created == 1
    assert native.calls[0][2] is native.calls[1][2]
    graph.close()
    graph.close()
    assert native.closed == 1
    with pytest.raises(RuntimeError, match='closed'):
        graph.invoke('third')
    graph.close()


def test_native_initialization_failure_releases_owned_tools(bridge, native):
    native.fail_initialize = True
    graph = bridge.create_graph()
    with pytest.raises(RuntimeError, match='native init failed'):
        graph.invoke('a document')
    assert native.created == 1 and native.closed == 1
    assert native.servers_started == 1 and native.servers_closed == 1
    graph.close()


def test_sync_api_refuses_active_async_loop_without_starting_tools(bridge, native):
    async def run():
        graph = bridge.create_graph()
        with pytest.raises(RuntimeError, match='ainvoke/aclose'):
            graph.invoke('a document')
        await graph.aclose()
    asyncio.run(run())
    assert native.created == 0


def test_server_startup_failure_closes_partial_service(bridge, native):
    native.fail_server = True
    graph = bridge.create_graph()
    with pytest.raises(RuntimeError, match='server startup failed'):
        graph.invoke('a document')
    graph.close()
    assert native.created == 0
    assert native.servers_started == native.servers_closed == 1


def test_native_cleanup_error_still_shuts_down_owned_server(bridge, native):
    native.fail_close = True
    graph = bridge.create_graph()
    graph.invoke('a document')
    with pytest.raises(RuntimeError, match='native close failed'):
        graph.close()
    assert graph._runner is None
    graph.close()
    assert native.closed == native.servers_closed == 1

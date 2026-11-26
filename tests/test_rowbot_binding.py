"""Row-Bot binding forwards live RunnableConfig without copying callback resources."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from langchain_core.callbacks import CallbackManager
from langchain_core.tools import tool

from agentbench.observe.langchain import TraceCallback
from agentbench.observe.store import TraceStore


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    relative = Path('resources/agents/67-row-bot/bindings/bridge.py')
    root = next(parent for parent in Path(__file__).parents if (parent / relative).is_file())
    spec = importlib.util.spec_from_file_location('rowbot_binding_under_test', root / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    captured = []

    @tool
    def read_fixture(path: str) -> str:
        """Read a local test file using a real LangChain tool lifecycle."""
        return (tmp_path / path).read_text(encoding='utf-8')

    def invoke_agent(prompt, enabled, config):
        captured.append(config)
        return read_fixture.invoke({'path': prompt}, config=config)

    package, agent = ModuleType('row_bot'), ModuleType('row_bot.agent')
    agent.invoke_agent = invoke_agent
    monkeypatch.setitem(sys.modules, 'row_bot', package)
    monkeypatch.setitem(sys.modules, 'row_bot.agent', agent)
    graph = module.RowBotGraph.__new__(module.RowBotGraph)
    graph._enabled = ['filesystem', 'calculator']
    (tmp_path / 'value.txt').write_text('TRACE_OK_42\n', encoding='utf-8')
    return graph, captured


@pytest.mark.parametrize('asynchronous', [False, True])
@pytest.mark.parametrize('manager', [False, True])
def test_live_callbacks_complete_config_and_caller_ownership(bridge, tmp_path, asynchronous, manager):
    graph, captured = bridge
    log = tmp_path / 'framework.jsonl'
    handler = TraceCallback(TraceStore(log, 'run', source='framework'))
    callbacks = CallbackManager([handler]) if manager else [handler]
    nested = {'thread_id': 'owned-thread', 'generation_id': 'owned-generation',
              'approval_mode': 'ask', 'custom_option': 'keep'}
    metadata = {'case_id': 'case', 'invocation_id': 'turn'}
    tags = ['audit']
    config = {'callbacks': callbacks, 'configurable': nested, 'metadata': metadata,
              'tags': tags, 'recursion_limit': 17, 'max_concurrency': 2}
    result = asyncio.run(graph.ainvoke('value.txt', config)) if asynchronous else graph.invoke('value.txt', config)
    assert result == 'TRACE_OK_42\n'
    forwarded = captured[0]
    assert forwarded is not config and forwarded['configurable'] is not nested
    for key in ('callbacks', 'metadata', 'tags'):
        assert forwarded[key] is config[key]
    assert forwarded['recursion_limit'] == 17 and forwarded['max_concurrency'] == 2
    assert forwarded['configurable'] == {**nested, 'runtime_surface': 'abb'}
    assert nested == {'thread_id': 'owned-thread', 'generation_id': 'owned-generation',
                      'approval_mode': 'ask', 'custom_option': 'keep'}
    assert metadata == {'case_id': 'case', 'invocation_id': 'turn'} and tags == ['audit']
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert [r['event'] for r in records] == ['span_start', 'span_end']
    assert records[0]['data']['kind'] == 'tool'
    assert records[0]['data']['input'] == {'path': 'value.txt'}
    assert records[1]['data']['output'] == 'TRACE_OK_42\n'
    assert records[0]['data']['span_id'] == records[1]['data']['span_id']
    assert records[0]['data']['metadata']['invocation_id'] == 'turn'


@pytest.mark.parametrize('asynchronous', [False, True])
def test_tool_failure_is_observed_and_still_propagates(bridge, tmp_path, asynchronous):
    graph, _ = bridge
    log = tmp_path / 'error.jsonl'
    config = {'callbacks': [TraceCallback(TraceStore(log, 'run', source='framework'))]}
    with pytest.raises(FileNotFoundError):
        if asynchronous:
            asyncio.run(graph.ainvoke('missing.txt', config))
        else:
            graph.invoke('missing.txt', config)
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert [r['event'] for r in records] == ['span_start', 'span_error']
    assert records[0]['data']['span_id'] == records[1]['data']['span_id']
    assert 'missing.txt' in records[1]['data']['error']


def test_missing_config_keeps_native_defaults(bridge):
    graph, captured = bridge
    assert graph.invoke('value.txt') == 'TRACE_OK_42\n'
    nested = captured[0]['configurable']
    assert nested['thread_id'].startswith('abb-')
    assert nested['generation_id']
    assert nested['runtime_surface'] == 'abb' and nested['approval_mode'] == 'approve'

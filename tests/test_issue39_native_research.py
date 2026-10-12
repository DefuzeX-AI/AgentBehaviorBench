"""Current GPT Researcher ChiefEditor boundary; transports are offline doubles."""
import asyncio
import sys
from types import ModuleType

import pytest

from tests.registered_agents import binding


@pytest.mark.parametrize('value', ['', None, {}, {'query': ''}, {'query': 3},
                                  {'query': 'current', 'messages': ['history']}])
def test_invalid_research_input_is_rejected_before_native_work(value):
    with pytest.raises(ValueError):
        asyncio.run(binding('gpt-researcher').run_research(value, {}))


@pytest.fixture
def native(monkeypatch):
    calls = []
    class ChiefEditor:
        def __init__(self, task, websocket, stream_output):
            assert websocket is None and stream_output is None
            self.task = task
            calls.append(self)
        def init_research_team(self):
            return self
        def compile(self):
            return self
        async def ainvoke(self, state, config):
            assert state['task'] is self.task
            self.config = config
            if isinstance(ChiefEditor.result, Exception):
                raise ChiefEditor.result
            return ChiefEditor.result
    ChiefEditor.result = {'report': '# Full native report\n' + 'word ' * 620}
    package = ModuleType('multi_agents')
    agents = ModuleType('multi_agents.agents')
    agents.ChiefEditorAgent = ChiefEditor
    monkeypatch.setitem(sys.modules, 'multi_agents', package)
    monkeypatch.setitem(sys.modules, 'multi_agents.agents', agents)
    return ChiefEditor, calls


def test_current_query_and_config_reach_fresh_native_tasks(native):
    cls, calls = native
    module = binding('gpt-researcher')
    config = {'metadata': {'case': 'a'}}
    for query in ('Remember ONLY ALPHA', 'Current BETA question'):
        result = asyncio.run(module.run_research({'query': query}, config))
        assert result['report'] is cls.result['report']
    assert calls[0] is not calls[1]
    assert [call.task['query'] for call in calls] == ['Remember ONLY ALPHA', 'Current BETA question']
    assert all(call.config is config for call in calls)
    assert all(call.task['include_human_feedback'] is False for call in calls)
    assert all(call.task['publish_formats'] == {'markdown': True, 'pdf': True, 'docx': True}
               for call in calls)


def test_compiled_binding_returns_complete_native_report(native):
    cls, _ = native
    graph = binding('gpt-researcher').create_graph()
    result = asyncio.run(graph.ainvoke({'query': 'Current question'}))
    assert result == {'query': 'Current question', 'report': cls.result['report']}


@pytest.mark.parametrize('result', [{}, RuntimeError('Native research failed')])
def test_missing_report_or_native_error_is_not_success(native, result):
    cls, _ = native
    cls.result = result
    with pytest.raises(KeyError if isinstance(result, dict) else RuntimeError) as caught:
        asyncio.run(binding('gpt-researcher').run_research({'query': 'current'}, {}))
    if isinstance(result, Exception):
        assert caught.value is result

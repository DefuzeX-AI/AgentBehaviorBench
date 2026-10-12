"""Current Article Explainer boundary; offline doubles are not certification."""
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from agentbench.harness.registry import tomllib
from tests.registered_agents import binding, unit


@pytest.mark.parametrize('value', ['', None, 5, {'message': 'question', 'pdf': '/some/file'},
                                  {'messages': ['synthetic history']}])
def test_unsupported_input_is_rejected_without_loading_native_dependencies(value):
    with pytest.raises(ValueError):
        binding('article-explainer').message_from_input(value)


def test_article_forwards_current_message_config_and_native_state(monkeypatch):
    module = binding('article-explainer')
    calls, checkpoints = [], []
    native_state = {'messages': ['native handoff', 'native final answer'], 'active_agent': 'summarizer'}
    class App:
        async def ainvoke(self, value, config):
            calls.append((value, config))
            return native_state
    def compile_graph(*, checkpointer):
        checkpoints.append(checkpointer)
        return App()
    native = ModuleType('explainer.graph')
    native.agent_swarm = SimpleNamespace(compile=compile_graph)
    monkeypatch.setitem(sys.modules, 'explainer', ModuleType('explainer'))
    monkeypatch.setitem(sys.modules, 'explainer.graph', native)
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-fixture')
    session, other = module.create_graph(), module.create_graph()
    config = {'callbacks': ['callback-token'], 'configurable': {'thread_id': 'case-a'}}
    try:
        assert asyncio.run(session.ainvoke('current excerpt', config)) is native_state
        assert asyncio.run(session.ainvoke({'message': 'another excerpt'}, config)) is native_state
        assert len(checkpoints) == 1
        assert calls == [({'messages': [{'role': 'user', 'content': text}]}, config)
                         for text in ('current excerpt', 'another excerpt')]
        assert all(actual_config is config for _, actual_config in calls)
        asyncio.run(other.ainvoke('another case', config))
        assert len(checkpoints) == 2 and checkpoints[0] is not checkpoints[1]
    finally:
        session.close()
        other.close()
    with pytest.raises(RuntimeError, match='closed'):
        session.invoke('later')


def test_native_article_failure_is_not_converted_to_a_successful_answer(monkeypatch):
    module = binding('article-explainer')
    failure = RuntimeError('Native swarm failed')
    class App:
        async def ainvoke(self, *args, **kwargs):
            raise failure
    session = module.create_graph()
    monkeypatch.setattr(session, '_load_app', lambda: App())
    try:
        with pytest.raises(RuntimeError) as caught:
            session.invoke('current excerpt')
        assert caught.value is failure
    finally:
        session.close()


def test_source_provenance_and_outer_onboarding_contract():
    root = unit('article-explainer')
    with (root / 'agent.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    provenance = json.loads((root / 'source-manifest.json').read_text())
    assert provenance['repository'] == manifest['source']['repository'] == (
        'https://github.com/duartecaldascardoso/article-explainer')
    assert provenance['revision'] == manifest['source']['revision'] == (
        '2cf067dc4b9158b03361c7b3e2544e067b75f1ae')
    assert manifest['source']['method'] == 'git'
    assert callable(binding('article-explainer').create_graph)
    assert 'output_key' not in manifest['adapter']
    assert not (root / 'evaluation/input-contract.json').exists()
    assert (root / 'README.md').is_file() and (root / 'requirement.md').is_file()

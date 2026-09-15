"""Offline adapter contracts; fixtures do not constitute Agent certification."""
import asyncio
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tomllib
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1] / 'resources/agents'
UNITS = {
    '05-waku-agent': {
        'repository': 'https://github.com/ShenSeanChen/waku-agent',
        'revision': 'a2fb2563ebeacf65596a34e6a73cfedb040f8a1b',
        'entrypoint': './waku/app.py:Waku',
        'binding': 'waku_binding.py:create_graph',
        'strategy': 'basic-safety-workflow',
    },
    '09-article-explainer': {
        'repository': 'https://github.com/duartecaldascardoso/article-explainer',
        'revision': '2cf067dc4b9158b03361c7b3e2544e067b75f1ae',
        'entrypoint': './explainer/graph.py:app',
        'binding': 'article_binding.py:create_graph',
        'strategy': 'CAND-002',
    },
}


def binding(unit, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / unit / 'bindings' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def waku(monkeypatch):
    calls, homes, connections = [], [], []

    @dataclass
    class Result:
        reply: str
        tool_calls: list
        iterations: int

    class Connection:
        closed = False
        def close(self):
            self.closed = True

    class Settings(SimpleNamespace):
        def ensure_home(self):
            self.home.mkdir(exist_ok=True)

    class Native:
        def __init__(self, settings, conn):
            assert settings.provider == 'openai'
            assert settings.base_url == 'https://api.openai.com/v1'
            assert settings.model == settings.small_model == 'model-a'
            assert settings.semantic_store == settings.episodic_store == 'sqlite'
            assert not any((settings.apple_calendar, settings.google_calendar,
                            settings.apple_tools, settings.gh_tool,
                            settings.experimental))
            self.settings, self.conn = settings, conn
            homes.append(settings.home)
            self.closed = False
        def respond(self, message, **kwargs):
            calls.append((message, kwargs))
            return Result(message, [{'tool': 'save_note', 'output': 'native fixture result'}], 2)
        def close(self):
            self.closed = True

    def connect(home, **kwargs):
        assert kwargs == {'check_same_thread': False}
        connection = Connection()
        connections.append(connection)
        return connection

    for name, attrs in {'waku': {}, 'waku.app': {'Waku': Native},
                        'waku.config': {'Settings': Settings}, 'waku.db': {'connect': connect}}.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-fixture-not-a-provider-key')
    return binding('05-waku-agent', 'waku_binding'), calls, homes, connections


def test_waku_preserves_current_input_native_result_and_closes_private_storage(waku):
    module, calls, homes, connections = waku
    session = module.create_graph()
    try:
        first = session.invoke(
            {'message': 'Keep this exact wording'},
            context={'model': 'model-a', 'small_model': 'model-a'},
        )
        native = session._native
        second = session.invoke('Second current message')
        assert first == {'reply': 'Keep this exact wording',
                         'tool_calls': [{'tool': 'save_note', 'output': 'native fixture result'}],
                         'iterations': 2}
        assert second['reply'] == 'Second current message'
        assert calls == [('Keep this exact wording', {'source': 'cli', 'stream': False}),
                         ('Second current message', {'source': 'cli', 'stream': False})]
        assert len(homes) == 1 and homes[0].is_dir()
    finally:
        session.close()
    assert native.closed and connections[0].closed and not homes[0].exists()
    session.close()
    with pytest.raises(RuntimeError, match='closed'):
        session.invoke('After close')


def test_waku_sessions_have_distinct_native_homes_and_constructor_failure_cleans_up(waku, monkeypatch):
    module, _, homes, connections = waku
    first, second = module.create_graph(), module.create_graph()
    try:
        context = {'model': 'model-a', 'small_model': 'model-a'}
        first.invoke('one', context=context)
        second.invoke('two', context=context)
        assert homes[0] != homes[1]
    finally:
        first.close()
        second.close()
    def failing_native(**kwargs):
        homes.append(kwargs['settings'].home)
        raise RuntimeError('Native initialization failed')
    monkeypatch.setattr(sys.modules['waku.app'], 'Waku', failing_native)
    failed = module.create_graph()
    with pytest.raises(RuntimeError, match='Native initialization failed'):
        failed.invoke('current input', context={'model': 'model-a', 'small_model': 'model-a'})
    assert connections[-1].closed and not homes[-1].exists()


@pytest.mark.parametrize('unit,name', [('05-waku-agent', 'waku_binding'),
                                      ('09-article-explainer', 'article_binding')])
@pytest.mark.parametrize('value', ['', None, 5, {'message': 'question', 'pdf': '/some/file'},
                                  {'messages': ['synthetic history']}])
def test_unsupported_input_is_rejected_without_loading_native_dependencies(unit, name, value):
    module = binding(unit, name)
    with pytest.raises(ValueError):
        module.message_from_input(value)


def test_article_forwards_only_current_message_callbacks_and_entire_native_state(monkeypatch):
    module = binding('09-article-explainer', 'article_binding')
    calls = []
    native_state = {'messages': ['native handoff', 'native final answer'], 'active_agent': 'summarizer'}
    class App:
        async def ainvoke(self, value, config):
            calls.append((value, config))
            return native_state
    native = ModuleType('explainer.graph')
    native.app = App()
    monkeypatch.setitem(sys.modules, 'explainer', ModuleType('explainer'))
    monkeypatch.setitem(sys.modules, 'explainer.graph', native)
    session = module.create_graph()
    config = {'callbacks': ['real callback token'], 'configurable': {'thread_id': 'case-a'}}
    assert asyncio.run(session.ainvoke('current excerpt', config)) is native_state
    assert asyncio.run(session.ainvoke({'message': 'another complete excerpt'}, config)) is native_state
    assert calls == [({'messages': [('user', 'current excerpt')]}, config),
                     ({'messages': [('user', 'another complete excerpt')]}, config)]
    session.close()
    with pytest.raises(RuntimeError, match='closed'):
        session.invoke('later')


def test_native_article_failure_is_not_converted_to_a_successful_answer(monkeypatch):
    module = binding('09-article-explainer', 'article_binding')
    failure = RuntimeError('Native swarm failed')
    class App:
        async def ainvoke(self, *args, **kwargs):
            raise failure
    native = ModuleType('explainer.graph')
    native.app = App()
    monkeypatch.setitem(sys.modules, 'explainer', ModuleType('explainer'))
    monkeypatch.setitem(sys.modules, 'explainer.graph', native)
    with pytest.raises(RuntimeError) as caught:
        module.create_graph().invoke('current excerpt')
    assert caught.value is failure


@pytest.mark.parametrize('unit', UNITS)
def test_source_manifest_matches_vendored_upstream_snapshot(unit):
    root = ROOT / unit
    expected = UNITS[unit]
    manifest = json.loads((root / 'source-manifest.json').read_text())
    agent = root / 'agent'

    assert manifest['repository'] == expected['repository']
    assert manifest['revision'] == expected['revision']
    assert manifest['branch'] == 'main'
    assert manifest['local_additions'] == ['abb-langgraph.json']
    recorded = {entry['path']: entry for entry in manifest['files']}
    actual = {
        path.relative_to(agent).as_posix()
        for path in agent.rglob('*')
        if path.is_file()
        and '__pycache__' not in path.parts
        and path.relative_to(agent).as_posix() not in manifest['local_additions']
    }
    assert set(recorded) == actual
    for name, entry in recorded.items():
        content = (agent / name).read_bytes()
        assert entry['bytes'] == len(content)
        assert entry['sha256'] == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize('unit', UNITS)
def test_complete_onboarding_contract_and_safe_source_tree(unit):
    root = ROOT / unit
    expected = UNITS[unit]
    manifest = tomllib.loads((root / 'agent.toml').read_text())
    graph_config = json.loads((root / 'agent' / manifest['adapter']['config']).read_text())

    assert manifest['source'] == {
        'repository': expected['repository'],
        'revision': expected['revision'],
        'downloaded_on': '2026-09-14',
    }
    assert manifest['adapter']['binding'] == expected['binding']
    assert 'output_key' not in manifest['adapter']
    assert graph_config['graphs'][manifest['adapter']['graph_id']] == expected['entrypoint']
    assert json.loads((root / 'evaluation/input-contract.json').read_text()) == {
        'encoding': 'identity'
    }
    profile = (root / 'requirement.md').read_text()
    assert f"id: {expected['strategy']}" in profile
    assert (root / 'README.md').is_file() and (root / 'requirement.md').is_file()
    assert not any(path.name == '.git' for path in root.rglob('*'))
    assert not any(path.is_symlink() for path in root.rglob('*'))
    assert not any(path.name == '.env' for path in root.rglob('*'))

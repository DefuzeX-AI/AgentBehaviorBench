"""TableGPT integration preserves callbacks and owns a writable per-Case profile."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def test_profile_is_private_and_cleanup_preserves_native_callbacks(tmp_path, monkeypatch):
    source = tmp_path / 'installed-profile'
    source.mkdir()
    (source / 'startup.py').write_text('original')
    captured = {}
    class Manager:
        def __init__(self, profile_dir):
            captured['profile'] = Path(profile_dir)
        async def shutdown_all(self, **kwargs):
            captured['shutdown'] = kwargs
    class Graph:
        async def ainvoke(self, value, *, config):
            captured['config'] = config
            return {'messages': [SimpleNamespace(content='native answer')]}
    monkeypatch.setitem(sys.modules, 'langchain_openai', SimpleNamespace(ChatOpenAI=lambda **_: object()))
    monkeypatch.setitem(sys.modules, 'langgraph.checkpoint.memory', SimpleNamespace(MemorySaver=lambda: object()))
    monkeypatch.setitem(sys.modules, 'pybox', SimpleNamespace(AsyncLocalPyBoxManager=Manager))
    monkeypatch.setitem(sys.modules, 'tablegpt', SimpleNamespace(DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR=source))
    monkeypatch.setitem(sys.modules, 'tablegpt.agent', SimpleNamespace(create_tablegpt_graph=lambda **_: Graph()))
    monkeypatch.setitem(sys.modules, 'langchain_core.messages', SimpleNamespace(HumanMessage=lambda **_: object()))
    path = Path(__file__).resolve().parents[1] / 'resources/agents/08-tablegpt-agent/bindings/bridge.py'
    spec = importlib.util.spec_from_file_location('tablegpt_binding_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    graph = module.create_graph()
    callback = object()
    config = {'callbacks': [callback], 'metadata': {'case': 'one'}, 'configurable': {'thread_id': 'case-session'}}
    async def exercise():
        answer = await graph.ainvoke('input', config=config)
        assert answer == {'answer': 'native answer'}
        (captured['profile'] / 'startup.py').write_text('case edit')
        await graph.aclose()
        await graph.aclose()
    asyncio.run(exercise())
    assert captured['config']['callbacks'][0] is callback
    assert captured['config']['metadata'] == config['metadata']
    assert captured['config']['configurable']['thread_id'] == 'case-session'
    assert captured['shutdown'] == {'now': True}
    assert not captured['profile'].exists()
    assert (source / 'startup.py').read_text() == 'original'

"""Issue #39: transport native report-chat state without building BBA history.

These boundary tests double app/research operations. Separate opt-in container
acceptance runs the original app, research, report store and chat.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import pytest


UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/04-gpt-researcher'


@pytest.fixture
def binding():
    spec = importlib.util.spec_from_file_location('native_chat_binding_test', UNIT / 'bindings/research.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_saved_once_and_only_current_messages_sent_to_native_chat(binding, monkeypatch):
    calls, research_queries, apps = [], [], []
    full_report = '# Original report\n' + 'word ' * 620
    tool_metadata = {'tool_calls': [{'tool': 'quick_search', 'sources': []}]}

    class API:
        def __init__(self):
            self.closed = False
            apps.append(self)

        async def post(self, path, payload):
            assert not self.closed
            calls.append((self, path, payload))
            if path == '/api/reports':
                return {'success': True, 'id': payload['id']}
            return {'success': True, 'response': {'content': 'Native chat: ' + payload['content'],
                                                  'metadata': tool_metadata}}

        def close(self):
            self.closed = True

    async def research(self, value, config=None):
        research_queries.append(value)
        return {'answer': full_report, 'sources': ['https://example.org/source']}

    monkeypatch.setattr(binding, 'NativeReportAPI', API)
    monkeypatch.setattr(binding.ResearchGraph, 'ainvoke', research)
    first, other = binding.create_graph(), binding.create_graph()

    async def execute():
        report = await first.ainvoke({'query': 'Research ALPHA'})
        chat = await first.ainvoke({'query': 'Explain that report'})
        isolated = await other.ainvoke({'query': 'Research BETA'})
        first.close()
        continued = await other.ainvoke({'query': 'Continue BETA'})
        return report, chat, isolated, continued

    try:
        report, chat, isolated, continued = asyncio.run(execute())
        assert report['answer'] == full_report
        assert chat['answer'] == 'Native chat: Explain that report'
        assert chat['metadata'] == tool_metadata
        assert continued['answer'] == 'Native chat: Continue BETA'
        assert research_queries == [{'query': 'Research ALPHA'}, {'query': 'Research BETA'}]
        assert report['report_id'] != isolated['report_id']
        assert [path for _, path, _ in calls] == [
            '/api/reports', f"/api/reports/{report['report_id']}/chat",
            '/api/reports', f"/api/reports/{isolated['report_id']}/chat"]
        assert calls[0][2] == {'id': report['report_id'], 'question': 'Research ALPHA',
                               'answer': full_report}
        assert calls[1][2] == {'role': 'user', 'content': 'Explain that report'}
        assert calls[3][2] == {'role': 'user', 'content': 'Continue BETA'}
        assert apps[0].closed and not apps[1].closed
        with pytest.raises(RuntimeError, match='closed'):
            asyncio.run(first.ainvoke('another input'))
    finally:
        first.close()
        other.close()
    assert all(api.closed for api in apps)


def test_native_chat_empty_response_is_not_normal_answer(binding):
    class API:
        async def post(self, path, payload):
            return {'success': True, 'response': {}}
        def close(self):
            pass

    session = binding.create_graph()
    session._api = API()
    session._report_id = 'existing-report'
    try:
        with pytest.raises(RuntimeError, match='empty response'):
            asyncio.run(session.ainvoke('Current input'))
    finally:
        session.close()


def test_original_app_constructor_gets_private_store_and_restores_environment(binding, monkeypatch):
    """Exercise production module/ASGI transport lifetime with a small app double."""
    import os

    stores, received = [], []

    class Loader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            path = Path(os.environ['REPORT_STORE_PATH'])
            stores.append(path)
            path.write_text('{}')
            async def app(scope, receive, send):
                body = b''
                while True:
                    event = await receive()
                    body += event.get('body', b'')
                    if not event.get('more_body', False):
                        break
                if scope['path'] == '/error':
                    response = {'error': 'Upstream route caught an error'}
                else:
                    payload = json.loads(body)
                    received.append(payload)
                    response = {'success': True, 'id': payload['id']}
                await send({'type': 'http.response.start', 'status': 200,
                            'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': json.dumps(response).encode()})
            module.app = app

    real_spec = importlib.util.spec_from_file_location

    def app_spec(name, path, **kwargs):
        if str(path).endswith('agent/backend/server/app.py'):
            return importlib.util.spec_from_loader(name, Loader())
        return real_spec(name, path, **kwargs)

    monkeypatch.setattr(importlib.util, 'spec_from_file_location', app_spec)
    monkeypatch.setenv('REPORT_STORE_PATH', '/original/deployment/path.json')
    first, second = binding.NativeReportAPI(), binding.NativeReportAPI()
    names = [first.module_name, second.module_name]
    try:
        assert stores[0] != stores[1]
        assert first.module is not second.module
        assert os.environ['REPORT_STORE_PATH'] == '/original/deployment/path.json'
        assert asyncio.run(first.post('/api/reports', {'id': 'A'}))['id'] == 'A'
        with pytest.raises(RuntimeError, match='did not complete'):
            asyncio.run(first.post('/error', {}))
        first.close()
        assert not stores[0].exists() and stores[1].exists()
        assert names[0] not in sys.modules and names[1] in sys.modules
        assert asyncio.run(second.post('/api/reports', {'id': 'B'}))['id'] == 'B'
        assert received == [{'id': 'A'}, {'id': 'B'}]
    finally:
        first.close()
        second.close()
    assert not any(path.exists() for path in stores)
    assert not any(name in sys.modules for name in names)


def test_native_chat_deployment_uses_supported_local_embedding_and_model_environment():
    config = json.loads((UNIT / 'bindings/research.json').read_text())
    dockerfile = (UNIT / 'Dockerfile').read_text()
    for name in ['EMBEDDING', 'SMART_LLM', 'FAST_LLM', 'STRATEGIC_LLM']:
        assert f'{name}={config[name]}' in dockerfile
    assert 'local_files_only' in dockerfile
    assert 'agent/frontend' not in (UNIT / '.dockerignore').read_text().splitlines()

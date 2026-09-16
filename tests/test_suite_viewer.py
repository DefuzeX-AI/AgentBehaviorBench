"""The live viewer shares durable Case state and confines recovery controls."""

from contextlib import contextmanager
import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from agentbench.cli import viewer, viewer_control
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.session import SuiteStore
from agentbench.observe.view_api import SuiteRunCatalogAPI


@pytest.fixture
def store(tmp_path):
    source = tmp_path / 'agent'
    source.mkdir()
    (source / 'agent.py').write_text('def run(value): return value\n')
    agents = [AgentRegistration(name, source, True, 'ready', 'test', 'test', 2)
              for name in ('alpha', 'beta')]
    with SuiteStore.begin(tmp_path / 'suites', 'suite_view', agents) as value:
        yield value


def artifact(tmp_path, run_id, *, suite_id='suite_view', attempt_id='attempt-1'):
    directory = tmp_path / 'runs' / run_id
    directory.mkdir(parents=True)
    (directory / 'run.json').write_text(json.dumps({
        'schema': 'abb.evaluate.run.v1', 'run_id': run_id, 'agent_id': 'alpha',
        'suite_id': suite_id, 'case_index': 0, 'attempt_id': attempt_id, 'status': 'failed'}))
    return directory


def start_attempt(store, directory, number):
    store.append({'event': 'case_attempt_started', 'agent_id': 'alpha', 'case_index': 0,
                  'attempt_id': f'attempt-{number}', 'attempt_number': number,
                  'artifact_run_id': directory.name, 'artifact_directory': str(directory)})


def test_canonical_reader_reopens_completed_suite_and_keeps_attempt_history(store, tmp_path):
    first = artifact(tmp_path, 'first')
    start_attempt(store, first, 1)
    store.append({'event': 'case_completed', 'agent_id': 'alpha', 'case_index': 0,
                  'attempt_id': 'attempt-1', 'case_result': {'status': 'failed',
                  'error': {'type': 'TimeoutError', 'message': 'temporary'}, 'case_index': 0}})
    store.append({'event': 'suite_completed', 'summary': {'failed': 1}})
    second = artifact(tmp_path, 'second', attempt_id='attempt-2')
    start_attempt(store, second, 2)
    result = viewer.parse_result_log(store.path)
    assert result['state'] == 'running'
    assert result['summary'] is None
    assert result['revision'] == len(result['events'])
    assert result['total_case_count'] == 4
    case = result['jobs'][0]['cases'][0]
    assert case['execution_status'] == 'retrying'
    assert [attempt['artifact_run_id'] for attempt in case['attempts']] == ['first', 'second']
    catalog = SuiteRunCatalogAPI(store.path).route('/api/observe/runs', {})
    assert catalog['jobs'] == result['jobs']
    assert {run['id'] for run in catalog['runs']} == {'first', 'second'}
    assert {run['attempt_id'] for run in catalog['runs']} == {'attempt-1', 'attempt-2'}


def test_attempt_catalog_rejects_foreign_suite_artifact(store, tmp_path):
    foreign = artifact(tmp_path, 'foreign', suite_id='another-suite')
    start_attempt(store, foreign, 1)
    assert SuiteRunCatalogAPI(store.path).route('/api/observe/runs', {})['runs'] == []


@contextmanager
def serving(path):
    server = viewer.create_viewer_server(path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(url, *, body=None, origin=None, token=None):
    headers = {}
    if origin is not None:
        headers['Origin'] = origin
    if token is not None:
        headers['X-ABB-Control-Token'] = token
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as response:
        return response.code, json.load(response)


def test_bound_control_checks_origin_token_and_route_before_dispatch(store, monkeypatch):
    class Controller:
        capabilities = {'can_control': True, 'control_url': '/api/suites/suite_view/commands',
                        'control_token': 'test-only'}
        calls = []

        def submit(self, payload, token, *, origin_valid):
            assert origin_valid
            if token != self.capabilities['control_token']:
                raise PermissionError('bad token')
            self.calls.append(payload)
            return {'command_id': payload['command_id'], 'status': 'accepted'}

    controller = Controller()
    monkeypatch.setattr(viewer_control, 'bound_controller', lambda path: controller)
    body = {'command_id': 'one', 'action': 'retry', 'agent_id': 'alpha', 'case_index': 0}
    with serving(store.path) as base:
        url = base + controller.capabilities['control_url']
        assert request(url, body=body, origin='https://evil.example', token='test-only')[0] == 403
        assert request(url, body=body, origin=base, token='wrong')[0] == 403
        assert request(base + '/api/suites/foreign/commands', body=body, origin=base, token='test-only')[0] == 409
        assert controller.calls == []
        assert request(url, body=body, origin=base, token='test-only')[0] == 202
        assert controller.calls == [body]
        status, snapshot = request(base + '/api/suites/suite_view/result', origin=base)
        assert status == 200 and snapshot['capabilities']['can_control']
        assert request(base + '/api/suites/suite_view/result', origin='https://evil.example')[0] == 403


def test_readonly_viewer_does_not_start_control_for_imported_history(store, monkeypatch):
    monkeypatch.setattr(viewer_control, 'bound_controller', lambda path: None)
    with serving(store.path) as base:
        status, snapshot = request(base + '/api/suites/suite_view/result')
        assert status == 200 and snapshot['capabilities'] == {'can_control': False}
        assert request(base + '/api/suites/suite_view/commands', body={'action': 'resume'}, origin=base)[0] == 403


@pytest.mark.parametrize('path', ['/api/suites/suite_view/result', '/api/observe/runs'])
@pytest.mark.parametrize('failure, write_number', [
    (BrokenPipeError, 1), (ConnectionResetError, 2),
])
def test_disconnected_viewer_client_does_not_send_another_response(store, path, failure, write_number):
    """A browser cancellation during headers or body must not trigger a fallback reply."""
    class DroppedConnection:
        writes = 0

        def write(self, payload):
            self.writes += 1
            if self.writes == write_number:
                raise failure('client disconnected')
            return len(payload)

    handler_type = viewer.build_viewer_handler(store.path, expected_suite_id='suite_view')
    handler = object.__new__(handler_type)
    handler.path = path
    handler.command = 'GET'
    handler.requestline = f'GET {path} HTTP/1.1'
    handler.request_version = 'HTTP/1.1'
    handler.headers = {'Host': '127.0.0.1:8765'}
    handler.wfile = DroppedConnection()

    handler.do_GET()

    assert handler.wfile.writes == write_number


def test_invalid_suite_snapshot_still_returns_service_error(store, monkeypatch):
    handler_type = viewer.build_viewer_handler(store.path, expected_suite_id='suite_view')
    handler = object.__new__(handler_type)
    handler.path = '/api/suites/suite_view/result'
    handler.command = 'GET'
    handler.requestline = 'GET /api/suites/suite_view/result HTTP/1.1'
    handler.request_version = 'HTTP/1.1'
    handler.headers = {'Host': '127.0.0.1:8765'}
    handler.wfile = io.BytesIO()

    def invalid_snapshot(_):
        raise ValueError('invalid snapshot')

    monkeypatch.setattr(viewer, 'parse_result_log', invalid_snapshot)
    handler.do_GET()

    response = handler.wfile.getvalue()
    assert b'503 Service Unavailable' in response
    assert b'Suite snapshot unavailable' in response


@pytest.mark.parametrize('headers, body', [
    ({'Content-Type': 'text/plain', 'Content-Length': '2'}, b'{}'),
    ({'Content-Type': 'application/json', 'Content-Length': '20000'}, b'{}'),
    ({'Content-Type': 'application/json', 'Content-Length': '2'}, b'[]'),
    ({'Content-Type': 'application/json', 'Content-Length': '2', 'Transfer-Encoding': 'chunked'}, b'{}'),
])
def test_control_reader_rejects_unbounded_or_wrong_shape_commands(headers, body):
    with pytest.raises(ValueError):
        viewer_control.read_command(headers, io.BytesIO(body))

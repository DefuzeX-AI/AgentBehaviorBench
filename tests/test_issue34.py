"""Issue #34: SDK classification is visible even without a network error."""
import json

import pytest

from agentbench.sdk.plugin.kuma.benchmark import read_result


@pytest.mark.parametrize('early,code', [(False, 'invalid_case_integrity'), (False, 'invalid_response'), (True, 'service_busy')])
def test_failed_container_exposes_sdk_error(tmp_path, early, code):
    directory = tmp_path/'host-run'
    (directory/'evaluation').mkdir(parents=True)
    (directory/'run.json').write_text(json.dumps({'run_id': directory.name, 'agent_id': 'agent', 'status': 'failed'}))
    error = {'type': 'ServiceError', 'code': code, 'message': 'SDK rejected the request', 'request_id': 'request'}
    file = 'error.json' if early else 'manifest.json'
    value = error if early else {'phase': 'judge', 'error': error}
    (directory/'evaluation'/file).write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match=code):
        read_result(directory, 'agent')


def test_malformed_diagnostics_do_not_mask_original_failure(tmp_path):
    directory = tmp_path/'host-run'
    (directory/'evaluation').mkdir(parents=True)
    (directory/'run.json').write_text(json.dumps({'run_id': directory.name, 'agent_id': 'agent', 'status': 'failed'}))
    (directory/'evaluation/manifest.json').write_text('{broken')
    with pytest.raises(RuntimeError, match='Container evaluation did not complete'):
        read_result(directory, 'agent')


def test_network_context_is_related_and_redacted(tmp_path):
    from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message
    (tmp_path/'evaluation').mkdir()
    (tmp_path/'evaluation/error.json').write_text(json.dumps({
        'code': 'invalid_response', 'message': 'synthetic-secret', 'type': 'ServiceError'}))
    rows = [
        {'event': 'tool_error', 'data': {'job_id': 'ours', 'host': 'sdk.example',
            'path': '/operations/one?token=synthetic-secret', 'error': 'connection failed', 'error_code': 'transport_error'}},
        {'event': 'tool_error', 'data': {'job_id': 'other', 'host': 'unrelated.example', 'error': 'unrelated'}},
    ]
    (tmp_path/'network.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    data = collect_artifacts(tmp_path, {'job_id': 'ours'}, environ={'KUMA_API_KEY': 'synthetic-secret'})
    assert data['sdk_error']['code'] == 'invalid_response'
    assert len(data['related_network_errors']) == 1
    message = failure_message(data)
    assert 'related network' in message and 'transport_error' in message
    assert 'synthetic-secret' not in json.dumps(data)
    assert '?' not in data['related_network_errors'][0]['path']


def test_symlink_diagnostics_are_not_read(tmp_path):
    from agentbench.sdk.plugin.kuma.diagnostics import read_diagnostic
    outside = tmp_path/'outside.json'
    outside.write_text('{"message":"untrusted outside file"}')
    root = tmp_path/'run'
    root.mkdir()
    (root/'error.json').symlink_to(outside)
    assert read_diagnostic(root, 'error.json') == {}
    assert read_diagnostic(root, '../outside.json') == {}

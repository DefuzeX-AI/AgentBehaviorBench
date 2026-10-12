"""SDK public errors survive generation, submission, and host diagnostics."""
import asyncio
import json
from types import MappingProxyType

import pytest
from kuma.errors import SensitiveDataError

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run
from tests.test_kuma_requirement import unit


def sdk_error():
    error = SensitiveDataError('Sensitive data was detected', details={
        'reasons': ('sensitive_credential_assignment:output',),
        'validation': MappingProxyType({'field': 'output', 'rule': 'credential_assignment'})})
    error.client_request_id = 'request-fixture'
    error.operation_id = 'operation-fixture'
    error._private_transport = 'must-not-be-saved'
    return error


def test_submission_error_details_reach_manifest_and_host(tmp_path, monkeypatch):
    error = sdk_error()
    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'succeeded', 'output': 'Original Agent output'}
    output = tmp_path / 'evaluation'
    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        def rejected_submit(**kwargs):
            raise error
        monkeypatch.setattr(run, 'submit', rejected_submit)
        summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
    saved = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    assert saved['error']['details']['reasons'] == ['sensitive_credential_assignment:output']
    assert saved['error']['operation_id'] == 'operation-fixture'
    assert saved['error']['phase'] == 'submission'
    assert saved['error']['input_id'] == 'input-0'
    assert saved['error']['client_request_id'] == 'request-fixture'
    assert '_private_transport' not in saved['error']
    assert summary['submission'] == 'failed' and summary['judge'] == 'pending'
    artifacts = collect_artifacts(tmp_path, {'status': 'failed'}, environ={})
    assert artifacts['sdk_error'] == saved['error']
    message = failure_message(artifacts)
    assert 'input-0' in message and 'sensitive_credential_assignment:output' in message


def test_generation_error_details_reach_error_collection_and_host(unit, tmp_path, monkeypatch):
    import kuma
    from agentbench.sdk.plugin.kuma.worker import execute
    error = sdk_error()
    def rejected_create(**kwargs):
        raise error
    monkeypatch.setattr(kuma, 'create_run', rejected_create)
    monkeypatch.setenv('KUMA_API_KEY', 'offline-not-sent')
    output = tmp_path / 'evaluation'
    assert asyncio.run(execute(unit, output, {'mode': 'generate', 'count': 1})) == 1
    saved = json.loads((output / 'error.json').read_text(encoding='utf-8'))
    collection = json.loads((output / 'case-collection.json').read_text(encoding='utf-8'))
    assert saved['details']['reasons'] == ['sensitive_credential_assignment:output']
    assert collection['attempt_failures'][0]['details'] == saved['details']
    assert collection['attempt_failures'][0]['operation_id'] == 'operation-fixture'
    assert saved['phase'] == 'case_generation'
    assert '_private_transport' not in saved
    assert collect_artifacts(tmp_path, {'status': 'failed'}, environ={})['sdk_error'] == saved


def test_host_keeps_structured_public_fields_and_full_message_with_redaction(tmp_path):
    secret = 'fixture-public-error-secret-123456789'
    message = 'Public explanation ' * 100
    public = {'type': 'ValidationError', 'message': message, 'code': 'invalid_response',
              'details': {'reasons': ['field_invalid'], 'api_key': secret,
                          'nested': [{'message': f'Backend rejected {secret}'}]},
              'retryable': False, 'status_code': 422, 'new_sdk_field': {'value': 'retained'}}
    Artifacts(tmp_path / 'evaluation', environ={}).save('error.json', public)
    artifacts = collect_artifacts(tmp_path, {'status': 'failed'}, environ={'KUMA_API_KEY': secret})
    assert artifacts['sdk_error']['message'] == message
    assert artifacts['sdk_error']['details']['api_key'] == '[REDACTED]'
    assert artifacts['sdk_error']['details']['nested'][0]['message'] == 'Backend rejected [REDACTED]'
    assert artifacts['sdk_error']['new_sdk_field'] == {'value': 'retained'}
    assert artifacts['sdk_error']['status_code'] == 422
    assert secret not in json.dumps(artifacts)
    assert len(failure_message(artifacts)) < 1000


def test_error_snapshot_bounds_bad_values_and_preserves_omission_metadata():
    from agentbench.sdk.plugin.kuma.error_artifacts import error_snapshot
    circular = {}
    circular['again'] = circular
    class Transport:
        def __str__(self):
            raise AssertionError('Do not stringify a transport object')
    error = {'code': 'fixture_error', 'details': {'cycle': circular, 'transport': Transport(),
             'many': list(range(10000)), 'large': 'x' * 1000000}}
    saved = error_snapshot(error, environ={})
    assert saved['code'] == 'fixture_error'
    omissions = {item['reason'] for item in saved['abb_diagnostic_omissions']}
    assert {'cycle', 'non_json_value', 'size_limit'} <= omissions
    assert len(json.dumps(saved)) < 512 * 1024


def test_large_message_is_explicitly_truncated_without_losing_classification():
    from agentbench.sdk.plugin.kuma.error_artifacts import exception_record
    error = SensitiveDataError('x' * 1000000, details={'reasons': ['output']})
    saved = exception_record(error, phase='submission', input_id='input-1')
    assert saved['code'] == 'sensitive_data_blocked'
    assert saved['phase'] == 'submission' and saved['input_id'] == 'input-1'
    assert '[ABB truncated]' in saved['message']
    assert saved['abb_diagnostic_omissions']
    assert len(json.dumps(saved)) < 512 * 1024


def test_existing_long_error_summary_is_bounded_but_saved_data_is_unchanged():
    public = {'type': 'ValidationError', 'message': 'explanation ' * 1000,
              'code': 'invalid_response', 'details': {'reasons': ['long_reason' * 1000]}}
    before = json.dumps(public)
    assert len(failure_message({'sdk_error': public})) < 1000
    assert json.dumps(public) == before


@pytest.mark.parametrize('phase', ['execution', 'judge'])
def test_non_submission_error_details_keep_the_correct_phase(tmp_path, monkeypatch, phase):
    error = sdk_error()
    output = tmp_path / 'evaluation'
    async def invoke(payload, folder, provider):
        if phase == 'execution':
            raise error
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'succeeded', 'output': 'Public output'}
    with sdk_run(tmp_path / 'repo', ['task'], judge=False) as (run, provider):
        if phase == 'judge':
            def rejected_judge():
                raise error
            monkeypatch.setattr(run, 'judge', rejected_judge)
        summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
    saved = summary['error']
    assert saved['phase'] == phase and saved['details']['reasons']
    if phase == 'execution':
        assert saved['input_id'] == 'input-0'
    else:
        assert 'input_id' not in saved, 'Case Judge errors must not be blamed on the last input'

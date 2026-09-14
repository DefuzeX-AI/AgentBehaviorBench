"""Issue #34: interrupted service requests use public recovery, never new work."""
from types import SimpleNamespace as NS
import json

import pytest

from agentbench.sdk.plugin.kuma.request_recovery import recover_request


def test_recovery_uses_original_request_without_create_run(monkeypatch, tmp_path):
    import kuma
    report = {'run_id': 'run', 'extensions': {'case_id': 'case'}, 'status': 'issue'}
    (tmp_path/'report.json').write_text(json.dumps(report))
    record = NS(run_id='run', case_id='case', status='succeeded', request_type='judgment',
                result_locator='report.json', to_dict=lambda: {'client_request_id': 'kreq_original'})
    calls = []
    monkeypatch.setattr(kuma, 'show_request', lambda *a, **kw: record)
    monkeypatch.setattr(kuma, 'resume_request', lambda *a, **kw: calls.append((a, kw)) or record)
    monkeypatch.setattr(kuma, 'create_run', lambda **kw: pytest.fail('must not recreate a paid Run'))
    result = recover_request(tmp_path, 'kreq_original', environ={'DEFUZEX_API_KEY': 'original'},
                             base_url='https://sdk.example', expected_run_id='run', expected_case_id='case')
    assert calls[0][0] == ('kreq_original',)
    assert calls[0][1]['repo_path'] == tmp_path and calls[0][1]['api_key'] == 'original'
    assert result['report'] == report and result['host_accepted'] is False


def test_mismatched_recovery_refuses_before_network(monkeypatch, tmp_path):
    import kuma
    monkeypatch.setattr(kuma, 'show_request', lambda *a, **kw: NS(run_id='different', case_id='case'))
    monkeypatch.setattr(kuma, 'resume_request', lambda *a, **kw: pytest.fail('must not contact service'))
    with pytest.raises(ValueError, match='run_id'):
        recover_request(tmp_path, 'kreq_original', environ={'KUMA_API_KEY': 'original'},
                        base_url='https://sdk.example', expected_run_id='run')


@pytest.mark.parametrize(('code', 'retryable'), [
    ('model_invalid_result', False),
    ('request_failed', False),
    ('service_busy', True),
])
def test_real_pypi_terminal_failure_recovery_never_starts_network(
    monkeypatch, tmp_path, code, retryable,
):
    """Replay the on-disk failure shape observed in the real campaign.

    Inputs are synthetic identities in the pinned SDK's request-record schema.
    ABB and the real PyPI show_request/resume_request implementations must return
    the original failed identity and preserve the error on disk, without creating
    a network client or promoting it to an accepted benchmark result. The SDK's
    public request summary does not expose error_code/error_retryable fields.
    """
    import kuma.requests

    request_id = 'kreq_' + 'a' * 32
    record = {
        'schema_version': 'kuma.request_record.v1',
        'client_request_id': request_id,
        'request_type': 'judgment',
        'status': 'failed',
        'operation_id': 'original-operation',
        'run_id': 'original-run',
        'case_id': 'original-case',
        'result_locator': None,
        'created_at': 1.0,
        'updated_at': 2.0,
        'idempotency_key': 'synthetic-original-key',
        'request_sha256': '0' * 64,
        'backend_sha256': '0' * 64,
        'api_key_sha256': '0' * 64,
        'case_validation': None,
        'error_code': code,
        'error_retryable': retryable,
    }
    directory = tmp_path / '.kuma' / 'requests'
    directory.mkdir(parents=True)
    path = directory / f'{request_id}.json'
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    monkeypatch.setattr(
        kuma.requests, 'BackendClient',
        lambda *a, **kw: pytest.fail('terminal failure must not start network I/O'),
    )

    result = recover_request(
        tmp_path, request_id, environ={'KUMA_API_KEY': 'unused-synthetic-key'},
        base_url='https://sdk.example', expected_run_id='original-run',
        expected_case_id='original-case',
    )

    assert result['request']['client_request_id'] == request_id
    assert result['request']['operation_id'] == 'original-operation'
    assert result['request']['status'] == 'failed'
    assert 'error_code' not in result['request']
    assert 'error_retryable' not in result['request']
    assert result['report'] is None and result['host_accepted'] is False
    assert 'idempotency_key' not in result['request']
    assert 'api_key_sha256' not in result['request']
    assert path.read_bytes() == before

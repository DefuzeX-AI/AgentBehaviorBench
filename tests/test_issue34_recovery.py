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

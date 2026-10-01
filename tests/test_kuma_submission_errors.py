"""Native failure text survives ABB's real KUMA submission boundary."""
import asyncio
import json

import pytest

from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run


@pytest.mark.parametrize('status, sdk_status', [
    ('failed', 'failed'), ('timeout', 'timeout'),
    ('cancelled', 'aborted'), ('aborted', 'aborted'),
])
@pytest.mark.parametrize('error', [
    "This request exceeds your plan's set usage limit.\n请稍后重试。",
    'Company editor completed without a non-empty report',
    '', None,
])
def test_native_error_reaches_committed_sdk_submission(tmp_path, status, sdk_status, error):
    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': status, 'error': error}

    output = tmp_path / 'evaluation'
    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
        assert summary['submission'] == 'committed'
        assert summary['judge'] == 'received'
        assert run.history[0].submission.status == sdk_status
        assert run.history[0].submission.error == error
    saved = json.loads((output / 'inputs/0001/submission.json').read_text(encoding='utf-8'))
    assert saved['error'] == error


def test_native_error_redacts_only_credentials_before_sdk_submission(tmp_path, monkeypatch):
    secret = 'fixture-submission-credential-12345'
    monkeypatch.setenv('TAVILY_API_KEY', secret)
    original = f'Quota exhausted.\nCredential: {secret}\nRetry later.'
    expected = 'Quota exhausted.\nCredential: [REDACTED]\nRetry later.'

    async def invoke(payload, folder, provider):
        (folder / 'otel-status.json').write_text('{"status":"complete"}')
        return {'status': 'failed', 'error': original}

    output = tmp_path / 'evaluation'
    with sdk_run(tmp_path / 'repo', ['task']) as (run, provider):
        submitted = []
        submit = run.submit

        def observe_submit(**kwargs):
            submitted.append(kwargs)
            return submit(**kwargs)

        monkeypatch.setattr(run, 'submit', observe_submit)
        summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
        assert summary['judge'] == 'received'
        assert submitted[0]['error'] == expected
        assert run.history[0].submission.error == expected
    result = json.loads((output / 'inputs/0001/result.json').read_text(encoding='utf-8'))
    assert result['error'] == expected

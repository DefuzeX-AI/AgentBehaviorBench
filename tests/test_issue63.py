"""Issue #63: a Judge poll that dies after submission leaves a recoverable request on record."""
import asyncio
import json

from agentbench.observe.invocation import InvocationObservation
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run


class DroppedPoll:
    """A real Run whose Judge status poll fails the way a dropped KUMA request does."""

    def __init__(self, run):
        self._run = run

    def __getattr__(self, name):
        if name == 'report':
            from kuma.errors import ServiceError
            # Verbatim from live runs: no client_request_id on a failed poll.
            raise ServiceError('The KUMA service request failed.', code='invalid_response', retryable=False)
        return getattr(self._run, name)


def _record(repo, run, request_id, *, status, updated_at):
    directory = repo / '.kuma' / 'requests'
    directory.mkdir(parents=True, exist_ok=True)
    failed = status == 'failed'  # The SDK only stores terminal failures with their code.
    (directory / f'{request_id}.json').write_text(json.dumps({
        'schema_version': 'kuma.request_record.v1', 'client_request_id': request_id,
        'request_type': 'judgment', 'status': status, 'operation_id': 'original-operation',
        'run_id': run.run_id, 'case_id': run.case_id, 'result_locator': None,
        'created_at': updated_at - 1, 'updated_at': updated_at,
        'idempotency_key': 'synthetic-original-key', 'request_sha256': '0' * 64,
        'backend_sha256': '0' * 64, 'api_key_sha256': '0' * 64, 'case_validation': None,
        'error_code': 'service_busy' if failed else None, 'error_retryable': True if failed else None}))


def _drive(run, provider, output, repo):
    async def invoke(payload, folder, shared_provider):
        observed = InvocationObservation(folder, 'invoke', run.run_id, 'langgraph', provider=shared_provider)
        observed.store.record('execution_start', input=payload)
        observed.store.record('execution_end', output='answer')
        observed.close()
        return {'status': 'succeeded', 'output': 'answer', 'raw_output': {}}
    return asyncio.run(drive_run(DroppedPoll(run), invoke, output, provider=provider, repo_path=repo))


def test_dropped_judge_poll_records_the_original_request_and_recovery_resumes_it(tmp_path):
    repo = tmp_path / 'repo'
    with sdk_run(repo, ['task']) as (run, provider):
        request_id = 'kreq_' + 'd' * 32
        _record(repo, run, request_id, status='running', updated_at=2.0)
        summary = _drive(run, provider, tmp_path / 'evaluation', repo)

    assert summary['judge'] == 'failed' and summary['error']['client_request_id'] is None
    assert summary['request']['client_request_id'] == request_id
    assert (summary['execution'], summary['submission'], summary['evidence']) == (
        'succeeded', 'committed', 'captured')

    # The host's own classifier now reaches the recovery it already implements.
    run_directory = tmp_path / 'run'
    files = Artifacts(run_directory, environ={})
    files.save('evaluation/manifest.json', summary)
    files.save('evaluation/case.json', {'case_id': summary['case_id']})
    host = {'status': 'failed', 'cleanup_status': 'succeeded', 'host_trace_validation': 'succeeded',
            'case_id': summary['case_id']}
    recovery = collect_artifacts(run_directory, host, environ={})['recovery']
    assert recovery == {'action': 'resume_request', 'automatic': True, 'phase': 'judge',
                        'client_request_id': request_id,
                        'reason': 'Resume the original Judge request without replaying Agent execution'}


def test_latest_judgment_record_of_the_run_is_chosen(tmp_path):
    repo = tmp_path / 'repo'
    with sdk_run(repo, ['task']) as (run, provider):
        _record(repo, run, 'kreq_' + 'e' * 32, status='failed', updated_at=2.0)
        _record(repo, run, 'kreq_' + 'f' * 32, status='running', updated_at=5.0)
        summary = _drive(run, provider, tmp_path / 'evaluation', repo)
    assert summary['request']['client_request_id'] == 'kreq_' + 'f' * 32


def test_records_of_other_runs_are_never_attached(tmp_path):
    repo = tmp_path / 'repo'
    with sdk_run(repo, ['task']) as (run, provider):
        other = type('Other', (), {'run_id': 'run_other', 'case_id': run.case_id})()
        _record(repo, other, 'kreq_' + 'a' * 32, status='running', updated_at=2.0)
        summary = _drive(run, provider, tmp_path / 'evaluation', repo)
    assert 'request' not in summary and summary['judge'] == 'failed'

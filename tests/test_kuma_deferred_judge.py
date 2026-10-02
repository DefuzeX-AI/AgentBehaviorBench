"""Real SDK evidence survives container/host handoff and durable Judge recovery."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from kuma import to_json

from agentbench.sdk.plugin.kuma.judge_bundle import export_context, restore_context
from agentbench.sdk.plugin.kuma.judge_tasks import prepare_task, judge_task
from agentbench.sdk.plugin.kuma.compatibility import run_case
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.contracts import PreparedCase
from agentbench.runtime.contracts.execution import RunControl
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import profile


class OfflineBackend:
    """Controlled Backend responses; the real SDK owns request serialization/ledger."""
    base_url = 'https://offline.example/api'
    api_key = 'dfx_offline_fixture_only'
    def __init__(self, case_id, verdict='pass'):
        self.case_id = case_id
        self.verdict = verdict
        self.posts = []
        self.polls = 0
        self.interrupt = False

    def json(self, method, path, *args, **kwargs):
        if path == '/sdk/judge/config/':
            return {'allowed_extensions': ['.json'], 'max_files': 20,
                    'max_file_bytes': 5 * 1024 * 1024, 'max_total_bytes': 8 * 1024 * 1024,
                    'manifest_schema_version': '1', 'evidence_types': ['raw_log', 'defuzex.runtime_evidence.capabilities.v1'],
                    'runtime_evidence_capabilities': ['runtime_evidence', 'agent_output', 'file_diff', 'runtime_trace']}
        if path.startswith('/sdk/v2/operations/'):
            self.polls += 1
            if self.interrupt:
                raise KeyboardInterrupt()
            return {'operation_id': 'operation-judge-offline', 'status': 'succeeded',
                    'result': {'judgment_id': 'judge-offline', 'case_id': self.case_id, 'status': self.verdict,
                               'confidence': 'high', 'issues': [], 'step_results': [], 'flags': {}}}
        raise AssertionError(path)

    def multipart(self, path, fields, parts, **kwargs):
        assert path == '/sdk/v2/judge/'
        self.posts.append((fields, parts, kwargs))
        return {'operation_id': 'operation-judge-offline', 'status': 'queued', 'poll_after_ms': 100}


def stage_task(root, *, native_failure=False):
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    repo = root / 'repo'
    run = create_run(repo_path=repo, agent_profile_path=profile(repo), allow_local=True,
        case_provider=lambda _: {'case_id': 'deferred-case', 'inputs': ['remember blue', 'recall']},
        judge=False, max_steps=2, track_files=True, upload_diff=True, trace_evidence=capture)
    directory = root / 'attempt'
    evaluation = directory / 'evaluation'
    case_json = run_case(run)
    Artifacts(evaluation).save('case.json', case_json)
    agent_id = 'fixture-agent'
    async def invoke(payload, folder, shared_provider):
        invocation = folder.name
        files = Artifacts(folder)
        with provider.get_tracer('fixture').start_as_current_span('write note') as operation:
            operation.set_attribute('gen_ai.operation.name', 'execute_tool')
            operation.set_attribute('gen_ai.tool.name', 'write')
            (repo / 'note.txt').write_text('blue', encoding='utf-8')
        files.save('request.json', {'agent_id': agent_id, 'run_id': invocation, 'session_id': run.run_id})
        files.save('otel-status.json', {'status': 'complete'})
        return {'schema': 'abb.result.v1', 'agent_id': agent_id, 'run_id': invocation,
                'status': 'failed' if native_failure else 'succeeded',
                **({} if native_failure else {'output': 'blue'}),
                **({'error_type': 'QuotaError', 'error': 'native quota exhausted'} if native_failure else {})}
    try:
        summary = asyncio.run(drive_run(run, invoke, evaluation, provider=provider,
            repo_path=repo, file_evidence_required=True, defer_judge=True))
        assert summary['judge'] == 'queued' and run.report is None
        Artifacts(evaluation).save('judge/context.json', export_context(run, case_json, upload_diff=True))
    finally:
        provider.shutdown()
    Artifacts(evaluation).save('process.json', {'sdk_base_url': OfflineBackend.base_url})
    registration = SimpleNamespace(agent_id=agent_id)
    prepared = PreparedCase(0, case_json['case_id'], content_sha256=case_content_sha256(case_json))
    Artifacts(directory).save('run.json', {'agent_id': agent_id, 'run_id': directory.name,
        'case_id': prepared.case_id, 'attempt_id': 'original-attempt', 'status': 'succeeded',
        'cleanup_status': 'succeeded', 'host_trace_validation': 'succeeded',
        'acceptance_fixture': 'offline isolated execution; no external model or tool traffic'})
    ticket = prepare_task(directory, prepared, environ={})
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'dfx_offline_fixture_only'}, control=RunControl())
    return runner, registration, prepared, ticket, summary


def test_real_sdk_defers_and_restores_all_committed_evidence(tmp_path):
    runner, agent, case, ticket, verification = stage_task(tmp_path)
    context_json = json.loads((ticket.directory / 'evaluation/judge/context.json').read_text(encoding='utf-8'))
    restored = restore_context(context_json)
    assert to_json(restored.history) == context_json['history']
    assert to_json(restored.case) == context_json['case']
    assert [item.submission.output for item in restored.history] == ['blue', 'blue']
    assert all(item.submission.extensions['trace_evidence'] for item in restored.history)
    assert all(item.submission.extensions['runtime_evidence'] for item in restored.history)


def test_host_sdk_judges_once_and_reuses_report_after_restart(tmp_path, monkeypatch):
    runner, agent, case, ticket, verification = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    first = judge_task(runner, agent, case, ticket)
    again = judge_task(runner, agent, case, ticket)
    assert first.passed and again.run_id == first.run_id
    assert len(backend.posts) == 1
    assert (ticket.directory / 'evaluation/judge/report.json').is_file()
    assert json.loads((ticket.directory / 'judge-task.json').read_text())['state'] == 'completed'


def test_interrupt_after_accepted_post_recovers_with_get_without_repost(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    backend.interrupt = True
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    with pytest.raises(KeyboardInterrupt):
        judge_task(runner, agent, case, ticket)
    backend.interrupt = False
    benchmark = judge_task(runner, agent, case, ticket)
    assert benchmark.passed and len(backend.posts) == 1


def test_modified_queued_evidence_is_rejected_before_any_sdk_upload(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    submission = ticket.directory / 'evaluation/inputs/0001/submission.json'
    submission.write_text('{}')
    with pytest.raises(ValueError, match='identity mismatch'):
        judge_task(runner, agent, case, ticket)
    assert backend.posts == []


def test_saved_report_validation_failure_is_rejected_without_resubmission(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    judge_task(runner, agent, case, ticket)
    report_path = ticket.directory / 'evaluation/judge/report.json'
    report = json.loads(report_path.read_text())
    report['extensions']['case_id'] = 'foreign-case'
    Artifacts(ticket.directory).save('evaluation/judge/report.json', report)
    with pytest.raises(RuntimeError, match='Case / Judge identity mismatch') as caught:
        runner.judge_case(agent, case, ticket)
    assert caught.value.artifacts['host_acceptance'] == 'rejected'
    assert caught.value.artifacts['recovery']['allow_replay'] is False
    assert 'received_report' not in caught.value.artifacts
    assert len(backend.posts) == 1


@pytest.mark.parametrize('verdict', ['pass', 'issue', 'insufficient_evidence'])
def test_native_failure_is_judged_but_report_does_not_promote_execution(tmp_path, monkeypatch, verdict):
    runner, agent, case, ticket, _ = stage_task(tmp_path, native_failure=True)
    backend = OfflineBackend(case.case_id, verdict)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    progress = []
    result = judge_task(runner, agent, case, ticket, on_progress=progress.append)
    assert len(backend.posts) == 1
    assert result.execution_status == 'failed' and result.passed is False
    assert result.report.status == verdict and result.host_acceptance == 'accepted'
    assert result.failures[0].error_type == 'QuotaError'
    assert result.failures[0].error_message == 'native quota exhausted'
    assert result.steps == () and result.history_count == 2
    assert progress[-1].stage == 'judge' and progress[-1].status == 'succeeded'
    assert json.loads((ticket.directory / 'run.json').read_text())['status'] == 'succeeded'
    assert json.loads((ticket.directory / 'judge-task.json').read_text())['state'] == 'completed'
    # A restart must reuse a received report without even constructing transport.
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kw: pytest.fail('No Judge resubmission'))
    again = judge_task(runner, agent, case, ticket)
    assert again.failures == result.failures and again.report.status == verdict


def test_legacy_failed_task_with_report_is_reconciled_offline(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path, native_failure=True)
    backend = OfflineBackend(case.case_id, 'issue')
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    judge_task(runner, agent, case, ticket)
    files = Artifacts(ticket.directory)
    host = json.loads((ticket.directory / 'run.json').read_text())
    task = json.loads((ticket.directory / 'judge-task.json').read_text())
    files.save('run.json', {**host, 'status': 'failed'})
    files.save('judge-task.json', {**task, 'state': 'failed'})
    monkeypatch.setattr('kuma.list_requests', lambda _: pytest.fail('No SDK I/O for saved report'))
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kw: pytest.fail('No transport'))
    result = judge_task(runner, agent, case, ticket)
    assert result.execution_status == 'failed' and result.host_acceptance == 'accepted'
    assert json.loads((ticket.directory / 'judge-task.json').read_text())['state'] == 'completed'
    assert json.loads((ticket.directory / 'run.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('field', ['cleanup_status', 'host_trace_validation'])
def test_saved_report_never_bypasses_original_host_gates(tmp_path, monkeypatch, field):
    runner, agent, case, ticket, _ = stage_task(tmp_path, native_failure=True)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    judge_task(runner, agent, case, ticket)
    files = Artifacts(ticket.directory)
    host = json.loads((ticket.directory / 'run.json').read_text())
    files.save('run.json', {**host, field: 'failed'})
    with pytest.raises(ValueError, match='original cleanup and host trace'):
        judge_task(runner, agent, case, ticket)
    assert len(backend.posts) == 1


def test_failed_submission_keeps_sdk_and_native_causes_instead_of_enqueue_error(tmp_path, monkeypatch):
    from dataclasses import replace
    runner, agent, case, ticket, summary = stage_task(tmp_path, native_failure=True)
    directory = ticket.directory
    (directory / 'judge-task.json').unlink()
    files = Artifacts(directory)
    host = json.loads((directory / 'run.json').read_text())
    files.save('run.json', {**host, 'status': 'failed', 'exit_code': 1,
                           'host_trace_validation': 'not_performed'})
    files.save('evaluation/manifest.json', {**summary, 'phase': 'submission',
        'submission': 'failed', 'evidence': 'pending', 'judge': 'pending',
        'error': {'type': 'SensitiveDataError', 'code': 'sensitive_data_blocked',
                  'message': 'Sensitive data blocked the original submission', 'retryable': False}})
    source = directory / 'prepared.json'
    source.write_text('{}', encoding='utf-8')
    import hashlib
    case = replace(case, artifact_path=source, artifact_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    agent.case_count = 1
    agent.path = tmp_path / 'repo'
    monkeypatch.setattr(runner, 'validate_sdk', lambda _: None)
    monkeypatch.setattr(runner, '_evaluate', lambda *args, **kw: directory)
    with pytest.raises(RuntimeError) as caught:
        runner.execute_case(agent, case)
    assert 'SensitiveDataError [sensitive_data_blocked]' in str(caught.value)
    assert 'native quota exhausted' in str(caught.value)
    assert 'Judge requires original cleanup' not in str(caught.value)
    assert caught.value.artifacts['sdk_error']['code'] == 'sensitive_data_blocked'
    assert caught.value.artifacts['native_failure']['error'] == 'native quota exhausted'
    assert not (directory / 'judge-task.json').exists()


def test_export_before_enqueue_is_recovered_without_agent_replay(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    (ticket.directory / 'judge-task.json').unlink()
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    monkeypatch.setattr(runner, '_evaluate', lambda *args, **kwargs: pytest.fail('Must not rerun Agent'))
    previous = SimpleNamespace(artifacts={'directory': str(ticket.directory)}, agent_id=agent.agent_id,
        case_id=case.case_id, case_index=case.case_index, attempt_id='original-attempt')
    result = runner.recover_case(agent, case, previous_result=previous)
    assert result.passed and len(backend.posts) == 1


def test_ledger_inspection_failure_preserves_primary_error_and_blocks_replacement(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    backend.interrupt = True
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    calls = []
    def inspect(_):
        calls.append(True)
        if len(calls) > 1:
            raise ValueError('damaged request ledger')
        return []
    monkeypatch.setattr('kuma.list_requests', inspect)
    with pytest.raises(KeyboardInterrupt) as caught:
        judge_task(runner, agent, case, ticket)
    assert len(backend.posts) == 1
    assert caught.value.artifacts['recovery']['automatic'] is False
    assert caught.value.artifacts['recovery']['allow_replay'] is False


def test_recovery_rejects_another_attempt_before_upload(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    previous = SimpleNamespace(artifacts={'directory': str(ticket.directory)}, agent_id=agent.agent_id,
        case_id=case.case_id, case_index=case.case_index, attempt_id='another-attempt')
    with pytest.raises(ValueError, match='another Case or Attempt'):
        runner.recover_case(agent, case, previous_result=previous)
    assert backend.posts == []


def test_missing_accepted_request_ledger_never_creates_a_replacement(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    backend.interrupt = True
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    with pytest.raises(KeyboardInterrupt):
        judge_task(runner, agent, case, ticket)
    monkeypatch.setattr('kuma.list_requests', lambda _: [])
    backend.interrupt = False
    with pytest.raises(ValueError, match='ledger is missing'):
        judge_task(runner, agent, case, ticket)
    assert len(backend.posts) == 1


def test_changed_credential_does_not_start_another_paid_judge(tmp_path, monkeypatch):
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    backend.interrupt = True
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    with pytest.raises(KeyboardInterrupt):
        judge_task(runner, agent, case, ticket)
    runner.environ['KUMA_API_KEY'] = 'dfx_changed_fixture_key'
    backend.interrupt = False
    with pytest.raises(ValueError, match='credential changed'):
        judge_task(runner, agent, case, ticket)
    assert len(backend.posts) == 1
    task = (ticket.directory / 'judge-task.json').read_text()
    assert 'dfx_offline_fixture_only' not in task and 'dfx_changed_fixture_key' not in task


@pytest.mark.parametrize('installed', ['0.3.2', None])
def test_host_sdk_dependency_is_checked_before_case_work(installed, monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from agentbench.sdk.plugin.kuma.configuration import validate_host_judge_dependency
    def version(_):
        if installed is None:
            raise PackageNotFoundError('kuma-defuzex')
        return installed
    monkeypatch.setattr('importlib.metadata.version', version)
    with pytest.raises(ValueError, match='Host Judge requires'):
        validate_host_judge_dependency()


def test_host_judge_job_preserves_validated_step_events_and_callbacks(tmp_path, monkeypatch):
    from agentbench.harness.events import EventBus
    from agentbench.harness.jobs import JudgmentJob, SuiteCallbacks, run_case_job
    runner, agent, case, ticket, _ = stage_task(tmp_path)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    events, completed = [], []
    job = JudgmentJob(agent, runner, case, {'agent_id': agent.agent_id, 'case_index': 0,
        'case_id': case.case_id, 'job_id': 'original-job', 'attempt_id': 'original-attempt'}, ticket=ticket)
    outcome = run_case_job(job, control=runner.control, bus=EventBus(on_event=events.append),
        callbacks=SuiteCallbacks(1, on_step_complete=lambda agent, step: completed.append(step.invocation.output)))
    assert outcome.result.status == 'succeeded' and completed == ['blue', 'blue']
    steps = [event for event in events if event['event'] == 'step_completed']
    assert len(steps) == 2
    assert all(event['attempt_id'] == 'original-attempt' and event['event_timing'] == 'artifact_replay' for event in steps)


def test_native_failure_report_survives_job_export_and_reopening(tmp_path, monkeypatch):
    from agentbench.harness.events import EventBus
    from agentbench.harness.jobs import JudgmentJob, SuiteCallbacks, run_case_job
    from agentbench.harness.session.codec import case_to_json, case_from_json
    from agentbench.harness.session.snapshot import suite_snapshot
    runner, agent, case, ticket, _ = stage_task(tmp_path, native_failure=True)
    backend = OfflineBackend(case.case_id)
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    rows, failed, completed = [], [], []
    identity = {'agent_id': agent.agent_id, 'case_index': 0, 'case_id': case.case_id,
                'job_id': 'original-job', 'attempt_id': 'original-attempt'}
    job = JudgmentJob(agent, runner, case, identity, ticket=ticket)
    outcome = run_case_job(job, control=runner.control, bus=EventBus(on_event=rows.append),
        callbacks=SuiteCallbacks(1, on_step_failure=lambda a, failure: failed.append(failure),
                                on_step_complete=lambda a, step: completed.append(step)))
    result = outcome.result
    assert result.execution_status == 'failed' and result.quality_gate == 'failed'
    assert result.judge_status == 'pass' and result.judge_delivery_status == 'received'
    assert result.host_acceptance == 'accepted' and result.error_type == 'QuotaError'
    assert len(failed) == 2 and completed == []
    exported = case_to_json(result)
    restored = case_from_json(exported)
    assert restored.benchmark.failures == result.benchmark.failures
    assert restored.execution_status == 'failed' and restored.quality_gate == 'failed'
    rows.append({**identity, 'event': 'case_completed', 'case_result': exported})
    snapshot = suite_snapshot({'suite_id': 'suite', 'agents': [{'agent_id': agent.agent_id, 'case_count': 1}]}, rows)
    reopened = snapshot['jobs'][0]['cases'][0]
    assert reopened['execution_status'] == 'failed' and reopened['judge_status'] == 'pass'
    assert reopened['stage'] == 'judge_completed' and reopened['judge_delivery_status'] == 'received'
    assert reopened['host_acceptance'] == 'accepted' and not reopened['can_retry']
    assert 'No Judge resubmission' in reopened['recovery_reason']


def test_viewer_revalidates_old_failed_reports_without_changing_logs_or_artifacts(tmp_path, monkeypatch):
    from dataclasses import replace
    import hashlib
    from agentbench.harness.session.snapshot import suite_snapshot
    from agentbench.harness.session.codec import json_value
    from agentbench.observe.result_reconciliation import reconcile_reports
    from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts
    runner, agent, case, ticket, _ = stage_task(tmp_path, native_failure=True)
    backend = OfflineBackend(case.case_id, 'issue')
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kwargs: backend)
    judge_task(runner, agent, case, ticket)
    files = Artifacts(ticket.directory)
    host = json.loads((ticket.directory / 'run.json').read_text())
    host.update(status='failed', suite_id='suite', case_index=0)
    files.save('run.json', host)
    task = json.loads((ticket.directory / 'judge-task.json').read_text())
    files.save('judge-task.json', {**task, 'state': 'failed'})
    artifacts = collect_artifacts(ticket.directory, host)
    artifacts['host_acceptance'] = 'rejected'
    artifacts['received_report']['host_accepted'] = False
    artifacts['recovery'] = {'action': 'blocked', 'allow_replay': False,
                            'reason': 'Resume the durable host Judge task without Agent replay'}
    source = ticket.directory / 'evaluation/case.json'
    prepared = replace(case, artifact_path=source, artifact_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    identity = {'agent_id': agent.agent_id, 'case_index': 0, 'case_id': case.case_id,
                'attempt_id': 'original-attempt', 'job_id': 'job'}
    rows = [{**identity, 'event': 'case_prepared', 'prepared_case': json_value(prepared)},
            {**identity, 'event': 'case_started', 'artifact_directory': str(ticket.directory)},
            {**identity, 'event': 'progress', 'stage': 'judge_wait', 'status': 'started'},
            {**identity, 'event': 'case_completed', 'case_result': {'status': 'failed',
                'execution_status': 'failed', 'error': {'type': 'RuntimeError', 'message': 'Container evaluation did not complete'},
                'artifacts': artifacts}}]
    plan = {'suite_id': 'suite', 'configuration': {'sdk': 'kuma'},
            'agents': [{'agent_id': agent.agent_id, 'case_count': 1}]}
    before = {p.relative_to(ticket.directory): p.read_bytes() for p in ticket.directory.rglob('*.json')}
    monkeypatch.setattr('kuma.list_requests', lambda _: pytest.fail('No ledger/transport calls'))
    monkeypatch.setattr('kuma.transport.backend.BackendClient', lambda **kw: pytest.fail('No transport'))
    projected = reconcile_reports(plan, rows, suite_snapshot(plan, rows))
    repaired = suite_snapshot(plan, projected)['jobs'][0]['cases'][0]
    assert repaired['execution_status'] == 'failed' and repaired['host_acceptance'] == 'accepted'
    assert repaired['judge_status'] == 'issue' and repaired['stage'] == 'judge_completed'
    assert repaired['error']['type'] == 'QuotaError' and not repaired['can_retry']
    assert rows[-1]['case_result']['artifacts']['host_acceptance'] == 'rejected'
    assert before == {p.relative_to(ticket.directory): p.read_bytes() for p in ticket.directory.rglob('*.json')}
    # A different Attempt or altered evidence must never be promoted in the view.
    files.save('run.json', {**host, 'attempt_id': 'foreign-attempt'})
    assert reconcile_reports(plan, rows, suite_snapshot(plan, rows)) is rows
    files.save('run.json', host)
    files.save('evaluation/inputs/0001/result.json', {})
    assert reconcile_reports(plan, rows, suite_snapshot(plan, rows)) is rows

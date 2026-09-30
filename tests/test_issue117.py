"""Completed behavioral findings remain distinct from execution and gate failures."""

from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from agentbench.cli.result_export import _summary_to_json, _suite_agent_to_json
from agentbench.cli.terminal_ui.presentation import print_agent_complete, print_suite_summary
from agentbench.harness.jobs import CaseJob, SuiteCallbacks, run_case_job
from agentbench.harness.result import BenchmarkResult, BenchmarkSuiteResult, CaseResult, SuiteAgentResult
from agentbench.harness.scheduling.retry import RetryPolicy
from agentbench.harness.session.codec import case_from_json, case_to_json, event_to_json
from agentbench.harness.session.snapshot import suite_snapshot
from agentbench.runtime.contracts.execution import RunControl
from agentbench.sdk.contracts import PreparedCase


def run_case(verdict, index=0):
    benchmark = BenchmarkResult('agent', 'fixture', f'run-{index}', 'report_ready',
        None if verdict is None else NS(status=verdict), (), 0,
        evidence_status='captured', host_acceptance='accepted', host_trace_validation='succeeded')
    job = CaseJob(NS(agent_id='agent'), NS(run_case=lambda *a, **kw: benchmark),
                  PreparedCase(index), {'job_id': f'job-{index}', 'agent_id': 'agent'})
    return run_case_job(job, control=RunControl(), bus=NS(publish=lambda *a, **kw: None),
                        callbacks=SuiteCallbacks(total=1)).result


@pytest.mark.parametrize('verdict,gate,code', [('pass', 'passed', 0), ('issue', 'failed', 1),
                                             ('insufficient_evidence', 'failed', 1)])
def test_worker_export_and_recovery_keep_execution_separate(verdict, gate, code):
    case = run_case(verdict)
    data = case_to_json(case)
    assert data['execution_status'] == 'completed'
    assert data['judge_status'] == verdict
    assert data['judge_delivery_status'] == 'received'
    assert data['evidence_status'] == 'captured'
    assert data['host_acceptance'] == 'accepted'
    assert data['host_trace_validation'] == 'succeeded'
    assert data['quality_gate'] == gate
    assert data['status'] == ('succeeded' if verdict == 'pass' else 'failed')  # Legacy contract.
    assert case_to_json(case_from_json(data)) == data
    assert not RetryPolicy().permits(case, 0)
    agent = SuiteAgentResult('agent', (case,))
    suite = BenchmarkSuiteResult('suite', ('agent',), (agent,))
    assert agent.execution_status == suite.execution_status == 'completed'
    assert agent.quality_gate == suite.quality_gate == gate
    assert suite.exit_code == code


def test_mixed_verdict_summary_and_both_event_serializers_agree():
    cases = tuple(run_case(verdict, i) for i, verdict in enumerate(('issue', 'issue', 'pass', 'pass')))
    agent = SuiteAgentResult('agent', cases, 4)
    suite = BenchmarkSuiteResult('suite', ('agent',), (agent,))
    summary = _summary_to_json(suite)
    assert summary['execution_status'] == 'completed'
    assert summary['execution_counts'] == {'completed': 1}
    assert summary['case_execution_counts'] == {'completed': 4}
    assert summary['judge_counts'] == {'issue': 2, 'pass': 2}
    assert summary['quality_gate'] == 'failed' and summary['exit_code'] == 1
    assert summary['failed'] == 1 and summary['suite_passed'] is False
    data = _suite_agent_to_json(agent)
    assert event_to_json({'item': agent})['item'] == data
    assert data['execution_status'] == 'completed' and data['quality_gate'] == 'failed'
    plan = {'suite_id': 'suite', 'agents': [{'agent_id': 'agent', 'case_count': 4}]}
    snapshot = suite_snapshot(plan, [event_to_json({'event': 'agent_completed', 'agent_id': 'agent', 'item': agent})])
    assert snapshot['jobs'][0]['execution_status'] == 'completed'
    assert snapshot['jobs'][0]['quality_gate'] == 'failed'
    output = []
    print_agent_complete(agent, output.append)
    print_suite_summary(suite, output.append)
    text = '\n'.join(output)
    assert 'Execution: COMPLETED' in text and 'Quality gate: FAILED' in text
    assert 'exit_code=1' in text and '0 passed, 1 failed' not in text


def test_retained_pass_does_not_pass_host_rejection():
    case = CaseResult('agent', 0, 'job', 'failed', error_type='TraceError', error_message='rejected',
        artifacts={'host_trace_validation': 'failed', 'completion': {'evidence': 'captured'},
                   'received_report': {'status': 'pass', 'host_accepted': False}})
    data = case_to_json(case)
    assert data['judge_status'] == 'pass' and data['judge_delivery_status'] == 'received'
    assert data['execution_status'] == 'blocked' and data['host_acceptance'] == 'rejected'
    assert data['quality_gate'] == 'failed' and data['evidence_status'] == 'captured'
    assert case_to_json(case_from_json(data)) == data


def test_missing_report_and_judge_service_failure_are_distinct():
    missing = run_case(None)
    assert missing.judge_delivery_status == 'missing' and missing.quality_gate == 'failed'
    failed = CaseResult('agent', 0, 'job', 'failed', error_type='JudgeError', error_message='unavailable',
                       artifacts={'judge_delivery_status': 'service_failure',
                                  'completion': {'execution': 'succeeded', 'evidence': 'captured'}})
    assert failed.judge_status is None and failed.judge_delivery_status == 'service_failure'
    assert failed.quality_gate == 'failed'
    execution_failure = replace(failed, artifacts={'completion': {'execution': 'failed'},
                                                 'host_acceptance': 'rejected'})
    assert execution_failure.execution_status == 'failed'


def test_old_results_do_not_invent_evidence_or_host_acceptance():
    benchmark = BenchmarkResult('agent', 'old-sdk', 'run', 'done', NS(status='issue'), (), 0)
    case = CaseResult('agent', 0, 'job', 'failed', benchmark=benchmark)
    data = case_to_json(case)
    for key in ('evidence_status', 'host_acceptance', 'host_trace_validation'):
        data.pop(key)
        data['benchmark'].pop(key)
    restored = case_from_json(data)
    assert restored.execution_status == 'completed'
    assert restored.host_acceptance == restored.evidence_status == 'unknown'
    plan = {'suite_id': 'suite', 'agents': [{'agent_id': 'agent', 'case_count': 1}]}
    snapshot = suite_snapshot(plan, [{'event': 'case_completed', 'agent_id': 'agent',
                                    'case_index': 0, 'case_result': case_to_json(restored)}])
    projected = snapshot['jobs'][0]['cases'][0]
    assert projected['host_acceptance'] == 'unknown'
    assert projected['quality_gate'] == 'failed'
    assert projected['judge_delivery_status'] == 'received'


def test_partial_cancelled_and_unattempted_work_cannot_complete_or_pass():
    case = run_case('pass')
    partial = SuiteAgentResult('agent', (case,), 2)
    assert partial.execution_status == 'skipped' and partial.quality_gate == 'failed'
    cancelled = SuiteAgentResult('agent', (CaseResult('agent', 0, 'job', 'cancelled'),))
    assert cancelled.execution_status == 'cancelled' and cancelled.quality_gate == 'failed'
    suite = BenchmarkSuiteResult('suite', ('agent', 'unattempted'), (SuiteAgentResult('agent', (case,)),))
    assert suite.execution_status == 'skipped' and suite.exit_code == 1
    assert suite.execution_counts == {'completed': 1, 'skipped': 1}


def test_explicit_host_rejection_never_passes_even_with_legacy_success():
    case = run_case('pass')
    rejected = replace(case, benchmark=replace(case.benchmark, host_acceptance='rejected'))
    assert rejected.quality_gate == 'failed'
    assert BenchmarkSuiteResult('suite', ('agent',), (SuiteAgentResult('agent', (rejected,)),)).exit_code == 1


@pytest.mark.parametrize('verdict', ['pass', 'issue', 'insufficient_evidence'])
def test_kuma_validated_artifacts_supply_acceptance_metadata(tmp_path, verdict):
    from agentbench.sdk.plugin.kuma.benchmark import read_result
    from tests.test_kuma_pypi import write_completed_case

    directory = tmp_path / 'host-run'
    write_completed_case(directory, 'agent', {'case_id': 'case', 'inputs': [
        {'input_id': 'input-1', 'payload': 'echo'}]})
    host_path = directory / 'run.json'
    host = json.loads(host_path.read_text())
    host['host_trace_validation'] = host['cleanup_status'] = 'succeeded'
    host_path.write_text(json.dumps(host))
    report_path = directory / 'evaluation/judge/report.json'
    report = json.loads(report_path.read_text())
    report['status'] = verdict
    report_path.write_text(json.dumps(report))
    benchmark = read_result(directory, 'agent')
    case = CaseResult('agent', 0, 'job', 'succeeded' if benchmark.passed else 'failed', benchmark=benchmark)
    assert case.execution_status == 'completed'
    assert case.host_acceptance == 'accepted' and case.host_trace_validation == 'succeeded'
    assert case.evidence_status == 'captured' and case.judge_delivery_status == 'received'
    assert case.quality_gate == ('passed' if verdict == 'pass' else 'failed')


@pytest.mark.parametrize('judge,expected', [('missing', 'missing'), ('failed', 'service_failure'),
                                          ('received', 'unknown')])
def test_kuma_diagnostics_do_not_claim_unvalidated_delivery(tmp_path, judge, expected):
    from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts

    (tmp_path / 'evaluation').mkdir()
    (tmp_path / 'evaluation/manifest.json').write_text(json.dumps({
        'phase': 'judge', 'execution': 'succeeded', 'evidence': 'captured', 'judge': judge}))
    artifacts = collect_artifacts(tmp_path, {'status': 'failed', 'host_trace_validation': 'succeeded'}, environ={})
    case = CaseResult('agent', 0, 'job', 'failed', artifacts=artifacts)
    assert case.judge_delivery_status == expected
    assert case.evidence_status == 'captured' and case.host_acceptance == 'rejected'
    assert case.quality_gate == 'failed'


@pytest.mark.parametrize('command', ['resume', 'reuse'])
def test_recovery_cli_uses_explicit_gate_even_with_legacy_success(tmp_path, monkeypatch, command):
    from agentbench.cli.features import resume, reuse

    module = resume if command == 'resume' else reuse
    case = run_case('pass')
    rejected = replace(case, benchmark=replace(case.benchmark, host_acceptance='rejected'))
    suite = BenchmarkSuiteResult('suite', ('agent',), (SuiteAgentResult('agent', (rejected,)),))
    assert suite.passed is True and suite.quality_gate == 'failed'
    monkeypatch.setattr(module, 'load_project_environment', lambda *a: None)
    monkeypatch.setattr(module, 'execution_environment_snapshot', lambda: NS(environ={}))
    monkeypatch.setattr(module, 'resolve_suite', lambda *a: tmp_path)
    if command == 'resume':
        monkeypatch.setattr(module, 'execute_recovery', lambda *a, **kw: suite)
    else:
        monkeypatch.setattr(module, 'execute_reuse', lambda *a, **kw: NS(result=suite, directory=tmp_path))
    args = NS(env_file=None, suite='suite', suite_root=None, output_root=None, model=None, max_steps=None)
    assert module.execute(args) == 1

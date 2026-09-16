"""Restart the public recovery entry using saved Cases and isolated fake workers."""

import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.cli.sessions.recovery import execute_recovery
from agentbench.harness import AgentRegistration, BenchmarkResult, ConcurrencySettings, SuiteRunner
from agentbench.harness.result import CaseResult
from agentbench.harness.session import SuiteStore, SuiteProvenanceError, read_snapshot
from agentbench.sdk.contracts import PreparedCase, PreparedCaseBatch


@pytest.fixture(autouse=True)
def isolated_reference_index(tmp_path, monkeypatch):
    from agentbench.cli.sessions import recovery
    monkeypatch.setattr(recovery, 'PROJECT_ROOT', tmp_path)


def make_agent(tmp_path, count):
    directory = tmp_path / 'agent-source'
    directory.mkdir()
    (directory / 'agent.py').write_text('def invoke(value): return value\n')
    return AgentRegistration('test-agent', directory, True, 'ready', 'fake', 'fixture', count)


def make_case(directory, index):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{index}.json'
    path.write_text(json.dumps({'case_id': f'case-{index}', 'inputs': [f'question-{index}', 'follow-up']}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return PreparedCase(index, f'case-{index}', path.resolve(), digest, digest)


def benchmark(agent, case, *, verdict='pass', run_id=None):
    return BenchmarkResult(agent.agent_id, 'fake', run_id or f'sdk-{case.case_index}', 'report_ready',
        SimpleNamespace(status=verdict, confidence=0.8, issues=(), evidence_gaps=()), (), 2)


def save_result(store, agent, case, *, verdict='pass', index=None):
    index = case.case_index if index is None else index
    identity = {'agent_id': agent.agent_id, 'case_index': index,
                'attempt_id': f'initial-{index}', 'attempt_number': 1, 'job_id': f'job-{index}'}
    store.append({'event': 'case_started', **identity})
    result = CaseResult(agent.agent_id, index, identity['job_id'], 'succeeded' if verdict == 'pass' else 'failed',
                         case.case_id, benchmark(agent, case, verdict=verdict),
                         attempt_id=identity['attempt_id'])
    store.append({'event': 'case_completed', **identity, 'case_result': result})


class RecoveryFactory:
    supports_concurrency = True
    trace_sink = None

    def __init__(self, directory):
        self.directory = directory
        self.executed, self.recovered, self.generated = [], [], []
        self.execute_error = None
        self.executed_at = []

    def open_suite(self, suite_id, control):
        outer = self
        class Session:
            def create(self, agent, identity, trace_sink):
                class Runner:
                    def validate_sdk(self, agent):
                        return 'fixture'
                    def prepare_cases(self, agent, **kwargs):
                        return self.prepare_case_batch(agent, case_indices=tuple(range(agent.case_count)), **kwargs).cases
                    def prepare_case_batch(self, agent, *, case_indices, **kwargs):
                        outer.generated.extend(case_indices)
                        return PreparedCaseBatch(tuple(make_case(outer.directory, index) for index in case_indices))
                    def run_case(self, agent, case, **kwargs):
                        saved = json.loads(case.artifact_path.read_text())
                        assert saved['case_id'] == case.case_id
                        outer.executed.append((case.case_index, case.case_id, dict(identity)))
                        outer.executed_at.append(time.time())
                        if outer.execute_error is not None:
                            raise outer.execute_error
                        return benchmark(agent, case)
                    def recover_case(self, agent, case, *, previous_result, **kwargs):
                        outer.recovered.append((case.case_index, previous_result, dict(identity)))
                        return benchmark(agent, case, run_id='original-sdk-run')
                return Runner()
            def close(self):
                pass
        return Session()


def runner_for(tmp_path):
    factory = RecoveryFactory(tmp_path / 'new-generation')
    return SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(3)), factory


def test_restart_thirty_cases_preserves_twenty_completed_and_executes_only_ten(tmp_path):
    agent = make_agent(tmp_path, 30)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_thirty', [agent]) as store:
        for index in range(30):
            case = store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', index))
            if index < 20:
                save_result(store, agent, case, verdict='issue' if index == 0 else 'pass')
        store.append({'event': 'suite_failed', 'error': {'type': 'KeyboardInterrupt', 'message': 'stopped'}})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert sorted(index for index, *_ in factory.executed) == list(range(20, 30))
    assert factory.generated == factory.recovered == []
    assert result.items[0].completed_case_count == 30
    assert result.items[0].case_results[0].benchmark.report.status == 'issue'
    snapshot = read_snapshot(directory)
    assert snapshot['counts']['completed'] == snapshot['counts']['judge_received'] == 30
    assert len(snapshot['jobs'][0]['cases']) == 30


def test_recovery_command_is_idempotent_across_separate_coordinators(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_command', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner, command_id='one-command')
    with pytest.raises(ValueError, match='already completed'):
        execute_recovery(directory, environ={}, runner=runner, command_id='one-command')
    assert len(factory.executed) == 1
    assert read_snapshot(directory)['commands'][-1]['status'] == 'completed'


def test_dispatched_attempt_is_reconciled_without_executing_agent_again(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_dispatched', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        store.append({'event': 'attempt_dispatched', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'original-attempt', 'attempt_number': 1,
                      'job_id': 'original-job', 'artifact_directory': str(tmp_path / 'original-run')})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == factory.generated == []
    assert len(factory.recovered) == 1
    _, previous, identity = factory.recovered[0]
    assert previous.artifacts['recovery']['action'] == 'inspect_attempt'
    assert identity['attempt_id'] == result.items[0].case_results[0].attempt_id == 'original-attempt'
    assert len(read_snapshot(directory)['jobs'][0]['cases'][0]['attempts']) == 1


def test_unlocated_dispatched_attempt_remains_blocked_even_with_explicit_replay(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_uncertain', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        store.append({'event': 'attempt_dispatched', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'unlocated', 'attempt_number': 1, 'job_id': 'job'})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner, replay=True)
    assert factory.executed == factory.recovered == factory.generated == []
    assert result.items[0].case_results[0].error_type == 'RecoveryRequired'


def test_missing_saved_file_blocks_only_its_case_and_keeps_other_cases_running(tmp_path):
    agent = make_agent(tmp_path, 2)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_missing', [agent]) as store:
        cases = [store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', index)) for index in range(2)]
        directory = store.directory
    cases[0].artifact_path.unlink()
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert [index for index, *_ in factory.executed] == [1]
    assert factory.generated == []
    assert result.items[0].case_results[0].error_type == 'RecoveryRequired'
    assert result.items[0].case_results[1].benchmark.report.status == 'pass'
    assert read_snapshot(directory)['jobs'][0]['cases'][0]['execution_status'] == 'blocked'


def test_restoring_exact_case_bytes_clears_only_the_artifact_block(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_restored', [agent]) as store:
        case = store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        directory = store.directory
    original = case.artifact_path.read_bytes()
    case.artifact_path.unlink()
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == []
    case.artifact_path.write_bytes(original)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert len(factory.executed) == 1 and result.items[0].case_results[0].execution_status == 'completed'


def test_in_memory_prepared_case_cannot_be_silently_reused_after_restart(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_memory', [agent]) as store:
        store.retain_case(agent.agent_id, PreparedCase(0, 'in-memory'))
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == factory.recovered == factory.generated == []
    assert 'only in memory' in result.items[0].case_results[0].error_message


def test_source_change_rejects_recovery_before_any_sdk_or_agent_work(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_changed', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        directory = store.directory
    (agent.path / 'agent.py').write_text('def invoke(value): return "new behavior"\n')
    runner, factory = runner_for(tmp_path)
    with pytest.raises(SuiteProvenanceError):
        execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == factory.recovered == factory.generated == []


def test_terminal_judge_failure_does_not_replay_but_unattempted_siblings_run(tmp_path):
    agent = make_agent(tmp_path, 2)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_terminal', [agent]) as store:
        for index in range(2):
            store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', index))
        store.append({'event': 'case_started', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'failed-judge', 'attempt_number': 1, 'job_id': 'job-0'})
        failed = CaseResult(agent.agent_id, 0, 'job-0', 'failed', 'case-0',
                            error_type='ModelInvalidResultError', error_message='model_invalid_result',
                            artifacts={'sdk_error': {'code': 'model_invalid_result', 'retryable': True}},
                            attempt_id='failed-judge')
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'attempt_id': 'failed-judge', 'case_result': failed})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert [index for index, *_ in factory.executed] == [1]
    assert factory.recovered == factory.generated == []
    assert result.items[0].case_results[0].error_message == 'model_invalid_result'


def test_unknown_generation_request_does_not_create_another_paid_request(tmp_path):
    agent = make_agent(tmp_path, 2)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_generation', [agent]) as store:
        failure = CaseResult(agent.agent_id, 0, 'generation-job', 'failed',
                             error_type='RequestStateUnknown', error_message='response lost',
                             artifacts={'phase': 'case_generation', 'sdk_error': {'code': 'unknown',
                                        'client_request_id': 'original-request', 'retryable': True}})
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'phase': 'generate', 'case_result': failure})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner)
    assert factory.generated == [1]
    assert [index for index, *_ in factory.executed] == [1]
    assert result.items[0].case_results[0].error_type == 'RequestStateUnknown'


def test_explicit_retry_still_cannot_replace_an_unknown_generation_operation(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_unknown_generation', [agent]) as store:
        failure = CaseResult(agent.agent_id, 0, 'generation-job', 'failed', error_type='RequestStateUnknown',
            error_message='Response lost', artifacts={'phase': 'case_generation', 'recovery': {
                'action': 'inspect_request', 'automatic': False, 'allow_replay': False}})
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'phase': 'generate', 'case_result': failure})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    result = execute_recovery(directory, environ={}, runner=runner, replay=True)
    assert factory.executed == factory.recovered == factory.generated == []
    assert result.items[0].case_results[0].error_type == 'RequestStateUnknown'
    assert read_snapshot(directory)['jobs'][0]['cases'][0]['can_retry'] is False


def test_retry_budget_survives_restart_during_the_last_scheduled_retry(tmp_path):
    from agentbench.harness.scheduling import RetryPolicy
    agent = make_agent(tmp_path, 1)
    recovery = {'action': 'replay_case', 'automatic': True}
    with SuiteStore.begin(tmp_path / 'suites', 'suite_retry_budget', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        for number in (1, 2):
            identity = {'agent_id': agent.agent_id, 'case_index': 0, 'job_id': f'job-{number}',
                        'attempt_id': f'attempt-{number}', 'attempt_number': number}
            store.append({'event': 'case_started', **identity})
            failed = CaseResult(agent.agent_id, 0, identity['job_id'], 'failed', 'case-0',
                error_type='ConnectionError', error_message='closed', artifacts={'recovery': recovery},
                attempt_id=identity['attempt_id'], attempt_number=number)
            store.append({'event': 'case_attempt_failed', **identity, 'case_result': failed})
            store.append({'event': 'retry_scheduled', **identity, 'retry_count': number, 'retry_at': 0})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    runner.retry_policy = RetryPolicy(max_retries=2, initial_delay=0, jitter=0)
    factory.execute_error = ConnectionError('still unavailable')
    factory.execute_error.recovery = recovery
    result = execute_recovery(directory, environ={}, runner=runner)
    assert len(factory.executed) == 1  # Already scheduled third Attempt; no fresh automatic budget.
    assert result.items[0].case_results[0].attempt_number == 3
    case = read_snapshot(directory)['jobs'][0]['cases'][0]
    assert case['retry_count'] == 2 and len(case['attempts']) == 3


def test_resume_preserves_the_remaining_retry_backoff(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_backoff', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        identity = {'agent_id': agent.agent_id, 'case_index': 0, 'job_id': 'original-job',
                    'attempt_id': 'original-attempt', 'attempt_number': 1}
        store.append({'event': 'case_started', **identity})
        failed = CaseResult(agent.agent_id, 0, 'original-job', 'failed', 'case-0',
            error_type='ConnectionError', error_message='closed',
            artifacts={'recovery': {'action': 'replay_case', 'automatic': True}},
            attempt_id='original-attempt')
        store.append({'event': 'case_attempt_failed', **identity, 'case_result': failed})
        due = time.time() + 0.12
        store.append({'event': 'retry_scheduled', **identity, 'retry_count': 1, 'retry_at': due})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner)
    assert len(factory.executed_at) == 1 and factory.executed_at[0] >= due


def test_cancelled_judge_retry_retains_request_and_resumes_original_attempt(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_cancelled_judge', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        identity = {'agent_id': agent.agent_id, 'case_index': 0, 'job_id': 'judge-job',
                    'attempt_id': 'judge-attempt', 'attempt_number': 1}
        store.append({'event': 'case_started', **identity})
        failed = CaseResult(agent.agent_id, 0, 'judge-job', 'failed', 'case-0',
            error_type='OperationTimeout', error_message='polling timed out',
            artifacts={'directory': str(tmp_path / 'original-run'),
                       'sdk_request': {'status': 'running', 'client_request_id': 'original-request'},
                       'recovery': {'action': 'resume_request', 'automatic': True}},
            attempt_id='judge-attempt')
        store.append({'event': 'case_attempt_failed', **identity, 'case_result': failed})
        store.append({'event': 'retry_scheduled', **identity, 'retry_count': 1, 'retry_at': time.time() + 60})
        store.append({'event': 'case_completed', **identity, 'case_result': failed})
        store.append({'event': 'case_retry_cancelled', **identity})
        directory = store.directory
    cancelled = read_snapshot(directory)['jobs'][0]['cases'][0]
    assert cancelled['execution_status'] == 'cancelled' and cancelled['retry_at'] is None
    assert cancelled['attempts'][0]['result']['artifacts']['sdk_request']['client_request_id'] == 'original-request'
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == factory.generated == []
    assert len(factory.recovered) == 1 and factory.recovered[0][2]['attempt_id'] == 'judge-attempt'


def test_prepared_case_cancelled_before_dispatch_can_continue_without_generation(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_cancelled_ready', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        skipped = CaseResult(agent.agent_id, 0, 'never-dispatched', 'skipped', 'case-0',
                             error_type='CaseSkipped', error_message='Cancelled before dispatch')
        store.append({'event': 'case_completed', 'agent_id': agent.agent_id, 'case_index': 0,
                      'case_result': skipped})
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner)
    assert len(factory.executed) == 1 and factory.generated == []
    assert len(read_snapshot(directory)['jobs'][0]['cases'][0]['attempts']) == 1


@pytest.mark.parametrize('recovering', [True, False])
def test_cancellation_before_worker_start_preserves_only_same_attempt_request_metadata(tmp_path, recovering):
    from agentbench.harness.events import EventBus
    from agentbench.harness.jobs import CaseJob, SuiteCallbacks, run_case_job
    from agentbench.runtime.contracts.execution import RunControl
    agent = make_agent(tmp_path, 1)
    case = make_case(tmp_path / 'generation', 0)
    previous = CaseResult(agent.agent_id, 0, 'previous-job', 'failed', case.case_id,
        error_type='OperationTimeout', error_message='polling timed out',
        artifacts={'sdk_request': {'client_request_id': 'original-request', 'status': 'running'},
                   'recovery': {'action': 'resume_request', 'automatic': True}},
        attempt_id='original-attempt')
    identity = {'agent_id': agent.agent_id, 'case_index': 0, 'job_id': 'current-job',
                'attempt_id': 'original-attempt' if recovering else 'new-attempt', 'attempt_number': 1}
    job = CaseJob(agent, SimpleNamespace(), case, identity, previous if recovering else None)
    control = RunControl()
    control.cancel()
    outcome = run_case_job(job, control=control, bus=EventBus(), callbacks=SuiteCallbacks(total=1))
    assert outcome.result.status == 'cancelled'
    if recovering:
        assert outcome.result.artifacts['sdk_request']['client_request_id'] == 'original-request'
        assert outcome.result.attempt_id == 'original-attempt'
    else:
        assert outcome.result.artifacts is None and outcome.result.attempt_id == 'new-attempt'


def test_resuming_an_old_external_suite_registers_its_cleanup_references(tmp_path):
    from agentbench.harness.session.references import collect_suite_references
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'external-history', 'suite_external', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        directory = store.directory
    assert collect_suite_references(tmp_path) == ()
    runner, _ = runner_for(tmp_path)
    execute_recovery(directory, environ={}, runner=runner)
    assert [entry.directory for entry in collect_suite_references(tmp_path)] == [directory]


def test_reference_registration_failure_closes_writer_before_any_execution(tmp_path, monkeypatch):
    from agentbench.cli.sessions import recovery
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_index_failure', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'generation', 0))
        directory = store.directory
    runner, factory = runner_for(tmp_path)
    def fail(*args, **kwargs):
        raise OSError('Index unavailable')
    monkeypatch.setattr(recovery, 'register_suite_reference', fail)
    with pytest.raises(OSError, match='Index unavailable'):
        execute_recovery(directory, environ={}, runner=runner)
    assert factory.executed == factory.generated == factory.recovered == []
    with SuiteStore.open(directory) as store:
        assert store.suite_id == 'suite_index_failure'

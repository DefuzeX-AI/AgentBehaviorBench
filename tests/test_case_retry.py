"""Retries preserve Case identity, verdicts and the shared scheduling budget."""

from collections import Counter
from types import SimpleNamespace

from agentbench.harness import SuiteRunner, ConcurrencySettings
from agentbench.harness.scheduling import AgentSeed, RetryPolicy
from agentbench.harness.result import CaseResult
from agentbench.sdk.contracts import PreparedCase, PreparedCaseBatch, PreparationFailure
from tests.test_suite_concurrency import Factory, agents, result


class TemporaryFailure(RuntimeError):
    recovery = {'action': 'replay_case', 'automatic': True, 'reason': 'Isolated fixture transport failed'}


def policy(retries=2, delay=0):
    return RetryPolicy(max_retries=retries, initial_delay=delay, jitter=0)


def test_temporary_failure_reuses_case_after_sibling_finishes():
    calls, sequence, events = Counter(), [], []
    def action(agent, case, *_):
        calls[case.case_id] += 1
        sequence.append(case.case_index)
        if case.case_index == 0 and calls[case.case_id] == 1:
            raise TemporaryFailure('temporary failure')
        return result(agent, case.case_index)
    suite = SuiteRunner(runner_factory=Factory(action), retry_policy=policy(delay=0.01)).run(
        agents(cases=2), on_event=events.append)
    assert suite.passed and sequence == [0, 1, 0]
    assert calls == {'agent-0-case-0': 2, 'agent-0-case-1': 1}
    starts = [event for event in events if event['event'] == 'case_started' and event['case_index'] == 0]
    assert [event['attempt_number'] for event in starts] == [1, 2]
    assert starts[0]['attempt_id'] != starts[1]['attempt_id']
    assert starts[0]['case_id'] == starts[1]['case_id']
    assert sum(event['event'] == 'case_completed' for event in events) == 2
    assert any(event['event'] == 'retry_scheduled' for event in events)


def test_exhausted_retry_keeps_single_terminal_case_and_attempt_history():
    calls, events = [], []
    def action(*_):
        calls.append(True)
        raise TemporaryFailure('still unavailable')
    suite = SuiteRunner(runner_factory=Factory(action), retry_policy=policy()).run(
        agents(cases=1), on_event=events.append)
    assert len(calls) == 3
    assert len(suite.items[0].case_results) == 1
    assert suite.items[0].case_results[0].attempt_number == 3
    assert sum(event['event'] == 'case_attempt_failed' for event in events) == 2
    assert sum(event['event'] == 'case_completed' for event in events) == 1


def test_issue_verdict_is_completed_and_never_retried():
    calls = []
    def action(agent, case, *_):
        calls.append(case.case_index)
        benchmark = result(agent, case.case_index)
        from dataclasses import replace
        return replace(benchmark, report=SimpleNamespace(status='issue'))
    suite = SuiteRunner(runner_factory=Factory(action), retry_policy=policy()).run(agents(cases=1))
    case = suite.items[0].case_results[0]
    assert calls == [0] and case.execution_status == 'completed'
    assert case.judge_status == 'issue' and not suite.passed


def test_resume_skips_preparation_and_retains_completed_verdicts():
    selected = agents(cases=3)
    previous = CaseResult('agent-0', 0, 'old-job', 'succeeded', 'agent-0-case-0', result(selected[0], 0))
    called = []
    factory = Factory(lambda agent, case, *_: (called.append(case.case_index), result(agent, case.case_index))[1])
    seed = AgentSeed(prepared={i: PreparedCase(i, f'agent-0-case-{i}') for i in range(3)},
                     results={0: previous}, attempts={1: 1})
    suite = SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(
        selected, resume_state={'agent-0': seed})
    assert suite.passed and sorted(called) == [1, 2]
    assert factory.prepared == []
    assert suite.items[0].case_results[0] is previous
    assert suite.items[0].case_results[1].attempt_number == 2


def test_partial_generation_runs_good_slots_without_renumbering():
    called = []
    factory = Factory(lambda agent, case, *_: (called.append(case.case_index), result(agent, case.case_index))[1])
    open_suite = factory.open_suite
    def open_partial(*args):
        session = open_suite(*args)
        create = session.create
        def create_partial(*args):
            runner = create(*args)
            runner.prepare_case_batch = lambda registration, **kwargs: PreparedCaseBatch(
                (PreparedCase(0, 'first'), PreparedCase(2, 'third')),
                (PreparationFailure(1, 'GenerationFailure', 'Second Case unavailable'),))
            return runner
        session.create = create_partial
        return session
    factory.open_suite = open_partial
    suite = SuiteRunner(runner_factory=factory).run(agents(cases=3))
    assert called == [0, 2]
    assert [case.status for case in suite.items[0].case_results] == ['succeeded', 'failed', 'succeeded']
    assert suite.items[0].case_results[2].case_id == 'third'


def test_cancel_during_backoff_preserves_failure_and_request_recovery():
    class PendingJudge(RuntimeError):
        recovery = {'action': 'resume_request', 'automatic': True, 'request_id': 'original-request'}

    factory = Factory(lambda *_: (_ for _ in ()).throw(PendingJudge('Judge still running')))
    original_open = factory.open_suite

    def open_suite(*args):
        session = original_open(*args)
        original_create = session.create

        def create(*args):
            runner = original_create(*args)
            runner.recover_case = lambda *_args, **_kwargs: None
            return runner

        session.create = create
        return session

    factory.open_suite = open_suite
    runner = SuiteRunner(runner_factory=factory, retry_policy=policy(delay=60))
    events = []

    def observe(event):
        events.append(event)
        if event['event'] == 'retry_scheduled':
            runner.cancel()

    suite = runner.run(agents(cases=1), on_event=observe)
    case = suite.items[0].case_results[0]
    assert case.error_type == 'PendingJudge'
    assert case.artifacts['recovery']['request_id'] == 'original-request'
    failed = next(event['case_result'] for event in events if event['event'] == 'case_attempt_failed')
    assert case == failed
    assert any(event['event'] == 'case_retry_cancelled' for event in events)
    assert not any(event.get('case_result') and event['case_result'].error_type == 'CaseSkipped' for event in events)


def test_shared_generation_block_pauses_queued_agents_but_runs_accepted_cases():
    calls, preparations = [], []
    factory = Factory(lambda agent, case, *_: (calls.append((agent.agent_id, case.case_index)),
                                             result(agent, case.case_index))[1])
    original_open = factory.open_suite

    def open_suite(*args):
        session = original_open(*args)
        original_create = session.create

        def create(*args):
            runner = original_create(*args)

            def prepare(registration, **kwargs):
                preparations.append(registration.agent_id)
                return PreparedCaseBatch((PreparedCase(0, 'retained-case'),),
                    (PreparationFailure(1, 'ServiceUnavailable', 'Generation service blocked',
                     artifacts={'recovery': {'pause_preparation': True}}),))

            runner.prepare_case_batch = prepare
            return runner

        session.create = create
        return session

    factory.open_suite = open_suite
    suite = SuiteRunner(runner_factory=factory).run(agents(count=2, cases=2))
    assert preparations == ['agent-0']
    assert calls == [('agent-0', 0)]
    assert len(suite.items) == 2
    assert all(case.error_type == 'CasePreparationPaused' for case in suite.items[1].case_results)

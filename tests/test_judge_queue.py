"""Execution slots are released while a bounded independent Judge queue drains."""
import threading
from dataclasses import replace

from agentbench.harness import SuiteRunner, ConcurrencySettings
from agentbench.sdk.judgment import DeferredJudgment
from tests.test_suite_concurrency import Factory, agents, result


class DeferredFactory(Factory):
    def __init__(self, directory, execute, judge):
        super().__init__()
        self.directory, self.execute, self.judge = directory, execute, judge

    def open_suite(self, suite_id, control):
        session = super().open_suite(suite_id, control)
        original = session.create
        def create(agent, identity, trace_sink):
            runner = original(agent, identity, trace_sink)
            runner.supports_deferred_judgment = True
            def execute_case(agent, case, **callbacks):
                self.execute(case.case_index, control)
                directory = self.directory / str(case.case_index)
                directory.mkdir(exist_ok=True)
                return DeferredJudgment(directory)
            def judge_case(agent, case, ticket, **callbacks):
                self.judge(case.case_index, control)
                return result(agent, case.case_index)
            runner.execute_case, runner.judge_case = execute_case, judge_case
            if hasattr(self, 'recover'):
                runner.recover_case = self.recover
            return runner
        session.create = create
        return session


def test_one_execution_slot_starts_next_case_while_judge_is_waiting(tmp_path):
    second = threading.Event()
    judged = []
    def execute(index, control):
        if index == 1:
            second.set()
    def judge(index, control):
        if index == 0:
            assert second.wait(3), 'Judge retained the only Docker execution slot'
        judged.append(index)
    events = []
    outcome = SuiteRunner(runner_factory=DeferredFactory(tmp_path, execute, judge),
        concurrency=ConcurrencySettings(1, 1, 2)).run(agents(), on_event=events.append)
    assert outcome.passed and judged == [0, 1]
    assert sum(e['event'] == 'judge_queued' for e in events) == 2
    assert sum(e['event'] == 'case_completed' for e in events) == 2


def test_queue_applies_backpressure_and_preserves_fifo(tmp_path):
    first_judge = threading.Event()
    release = threading.Event()
    executed, judged = [], []
    def execute(index, control):
        executed.append(index)
    def judge(index, control):
        if index == 0:
            first_judge.set()
            assert release.wait(3)
        judged.append(index)
    def tick():
        if first_judge.is_set() and len(executed) == 3:
            # One active Judge plus two queued/reserved executions fills capacity.
            release.set()
    outcome = SuiteRunner(runner_factory=DeferredFactory(tmp_path, execute, judge),
        concurrency=ConcurrencySettings(1, 1, 2)).run(agents(cases=5), on_tick=tick)
    assert outcome.passed and executed == judged == list(range(5))


def test_cancelled_queue_retains_recoverable_tickets_without_agent_replay(tmp_path):
    queued = []
    runner = SuiteRunner(runner_factory=DeferredFactory(tmp_path, lambda *_: None, lambda *_: None),
                         concurrency=ConcurrencySettings(1, 1, 1))
    def event(value):
        if value['event'] == 'judge_queued':
            queued.append(value)
            runner.cancel()
    outcome = runner.run(agents(), on_event=event)
    pending = outcome.items[0].case_results[0]
    assert len(queued) == 1
    assert pending.artifacts['recovery']['action'] == 'resume_request'
    assert pending.artifacts['recovery']['allow_replay'] is False
    assert pending.attempt_id == queued[0]['attempt_id']


def test_judge_configuration_is_validated_and_read_from_environment():
    settings = ConcurrencySettings.from_environ({'ABB_MAX_PARALLEL_JUDGES': '3', 'ABB_JUDGE_QUEUE_CAPACITY': '4'})
    assert settings.max_parallel_judges == 3 and settings.judge_queue_capacity == 4


def test_recovered_judge_uses_original_attempt_and_independent_pool(tmp_path):
    from agentbench.harness.result import CaseResult
    from agentbench.harness.scheduling.state import AgentSeed
    from agentbench.sdk.contracts import PreparedCase
    case = PreparedCase(0, 'agent-0-case-0')
    previous = CaseResult('agent-0', 0, 'original-job', 'failed', case_id=case.case_id,
        attempt_id='original-attempt', artifacts={'directory': str(tmp_path), 'recovery': {'action': 'resume_request'}})
    recovered = []
    def no_execution(*args):
        raise AssertionError('Recovery replayed the Agent')
    factory = DeferredFactory(tmp_path, no_execution, no_execution)
    def recover(agent, selected, *, previous_result, **callbacks):
        recovered.append((previous_result.attempt_id, threading.current_thread().name))
        return result(agent, selected.case_index)
    factory.recover = recover
    seed = AgentSeed(prepared={0: case}, recoveries={0: previous}, attempts={0: 1})
    outcome = SuiteRunner(runner_factory=factory).run(agents(cases=1), resume_state={'agent-0': seed})
    assert outcome.passed and recovered[0][0] == 'original-attempt'
    assert recovered[0][1].startswith('abb-judge')


def test_judge_concurrency_is_independent_and_bounded(tmp_path):
    barrier = threading.Barrier(2)
    active = peak = 0
    lock = threading.Lock()
    def judge(index, control):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(3)
        with lock:
            active -= 1
    outcome = SuiteRunner(runner_factory=DeferredFactory(tmp_path, lambda *_: None, judge),
        concurrency=ConcurrencySettings(1, 2, 4)).run(agents(cases=4))
    assert outcome.passed and peak == 2

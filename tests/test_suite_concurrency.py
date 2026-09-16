"""Behavioral tests for the preparation/Case pipeline and its global bound."""

from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from agentbench.harness import AgentRegistration, BenchmarkResult, SuiteRunner, ConcurrencySettings
from agentbench.harness.errors import SuiteConfigurationError
from agentbench.sdk.contracts import PreparedCase
from agentbench.runtime.contracts.execution import RuntimeInfrastructureError


def agents(count=1, cases=2):
    return tuple(AgentRegistration(f"agent-{i}", Path("."), True, "ready", "fake", "test", cases)
                 for i in range(count))


def result(agent, index, *, passed=True):
    return BenchmarkResult(agent.agent_id, "test", f"{agent.agent_id}-{index}", "report_ready",
                           SimpleNamespace(status="pass" if passed else "fail"), (), 0)


class Factory:
    supports_concurrency = True
    trace_sink = None

    def __init__(self, action=None, prepare=None, validate=None):
        self.action = action or (lambda agent, case, *_: result(agent, case.case_index))
        self.prepare = prepare
        self.validate = validate or (lambda agent: "test")
        self.sessions = []
        self.created = []
        self.prepared = []

    def open_suite(self, suite_id, control):
        outer = self
        class Session:
            closed = False
            def create(self, registration, identity, trace_sink):
                runner = SimpleNamespace(validate_sdk=outer.validate)
                outer.created.append((runner, dict(identity)))
                def prepare_cases(agent, **callbacks):
                    outer.prepared.append(agent.agent_id)
                    if outer.prepare:
                        return outer.prepare(agent, control, callbacks)
                    return tuple(PreparedCase(i, f"{agent.agent_id}-case-{i}")
                                 for i in range(agent.case_count))
                def run_case(agent, case, **callbacks):
                    return outer.action(agent, case, control, callbacks, trace_sink)
                runner.prepare_cases = prepare_cases
                runner.run_case = run_case
                return runner
            def close(self):
                self.closed = True
        session = Session()
        self.sessions.append(session)
        return session


def test_single_agent_two_cases_really_overlap_with_independent_runners():
    both = threading.Barrier(2)
    worker_threads = []
    callback_threads = []
    coordinator = threading.get_ident()
    def action(agent, case, *_):
        worker_threads.append(threading.get_ident())
        both.wait(3)
        return result(agent, case.case_index)
    factory = Factory(action)
    outcome = SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(
        agents(), on_event=lambda event: callback_threads.append(threading.get_ident()))
    assert outcome.passed and len(outcome.items) == 1
    assert len(set(worker_threads)) == 2
    assert set(callback_threads) == {coordinator}
    assert factory.prepared == ["agent-0"]
    assert len(factory.created) == 3  # One preparer, two Case runners.
    assert len({id(runner) for runner, _ in factory.created}) == 3
    identities = [identity for _, identity in factory.created if identity["phase"] == "execute"]
    assert identities[0]["job_id"] != identities[1]["job_id"]
    assert identities[0]["agent_job_id"] == identities[1]["agent_job_id"]
    assert [case.case_index for case in outcome.items[0].case_results] == [0, 1]


def test_free_case_slot_refills_before_slow_sibling_and_agent_finishes_once():
    both = threading.Barrier(2)
    third = threading.Event()
    completion_order = []
    agents_completed = []
    def action(agent, case, *_):
        if case.case_index < 2:
            both.wait(3)
        if case.case_index == 0:
            assert third.wait(3), "The next Case was not dispatched into the free slot"
        if case.case_index == 2:
            third.set()
        return result(agent, case.case_index)
    def event(value):
        if value["event"] == "case_completed":
            completion_order.append(value["case_index"])
    outcome = SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(
        agents(cases=3), on_event=event, on_agent_complete=agents_completed.append)
    assert completion_order[0] == 1
    assert len(agents_completed) == 1
    assert [case.case_index for case in outcome.items[0].case_results] == [0, 1, 2]
    assert outcome.items[0].completed_case_count == 3


def test_preparation_and_execution_share_one_global_limit_across_agents():
    active = peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(2)
    first_execution = threading.Event()
    def enter():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
    def leave():
        nonlocal active
        with lock:
            active -= 1
    def prepare(agent, control, callbacks):
        enter()
        try:
            if agent.agent_id in {"agent-0", "agent-1"}:
                barrier.wait(3)
            if agent.agent_id == "agent-1":
                assert first_execution.wait(3), "An all-Agent preparation barrier blocked ready Cases"
            return tuple(PreparedCase(i, f"{agent.agent_id}-{i}") for i in range(agent.case_count))
        finally:
            leave()
    def action(agent, case, *_):
        enter()
        try:
            first_execution.set()
            return result(agent, case.case_index)
        finally:
            leave()
    outcome = SuiteRunner(runner_factory=Factory(action, prepare), concurrency=ConcurrencySettings(2)).run(agents(4))
    assert peak == 2 and active == 0 and outcome.passed
    assert [item.agent_id for item in outcome.items] == [f"agent-{i}" for i in range(4)]


def test_case_failure_keeps_successful_siblings_and_continues_pending_cases():
    def action(agent, case, *_):
        if case.case_index == 1:
            raise ValueError("Case failed")
        return result(agent, case.case_index)
    outcome = SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(agents(cases=3))
    item, = outcome.items
    assert [case.status for case in item.case_results] == ["succeeded", "failed", "succeeded"]
    assert item.completed_case_count == 2 and item.attempted_case_count == 3
    assert item.error_type == "ValueError" and not item.passed


def test_fail_fast_stops_pending_cases_but_allows_inflight_case_to_finish():
    both = threading.Barrier(2)
    failed = threading.Event()
    called = []
    def action(agent, case, control, *_):
        called.append(case.case_index)
        both.wait(3)
        if case.case_index == 0:
            return result(agent, case.case_index, passed=False)
        assert failed.wait(3)
        assert not control.cancelled
        return result(agent, case.case_index)
    def event(value):
        if value["event"] == "case_completed" and value["case_index"] == 0:
            failed.set()
    outcome = SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(
        agents(cases=4), continue_on_error=False, on_event=event)
    assert sorted(called) == [0, 1]
    assert [case.status for case in outcome.items[0].case_results] == ["failed", "succeeded", "skipped", "skipped"]


def test_preparation_failure_never_runs_its_cases_and_other_agent_continues():
    called = []
    def prepare(agent, *_):
        if agent.agent_id == "agent-0":
            raise ValueError("batch failed")
        return tuple(PreparedCase(i) for i in range(agent.case_count))
    def action(agent, case, *_):
        called.append(agent.agent_id)
        return result(agent, case.case_index)
    outcome = SuiteRunner(runner_factory=Factory(action, prepare), concurrency=ConcurrencySettings(2)).run(agents(2))
    assert called == ["agent-1", "agent-1"]
    assert outcome.items[0].preparation_error.error_type == "ValueError"
    assert all(case.status == "skipped" for case in outcome.items[0].case_results)
    assert outcome.items[1].passed


def test_invalid_prepared_batch_is_rejected_before_case_execution():
    called = []
    factory = Factory(lambda *args: called.append(args), lambda *_: (PreparedCase(0),))
    outcome = SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(agents())
    assert not called
    assert outcome.items[0].preparation_error.error_type == "ValueError"


def test_shared_injected_runner_is_rejected_for_two_cases_of_one_agent():
    runner = SimpleNamespace(validate_sdk=lambda a: "test",
                             prepare_cases=lambda a, **kw: (PreparedCase(0),),
                             run_case=lambda a, case, **kw: result(a, case.case_index))
    with pytest.raises(SuiteConfigurationError, match="runner factory"):
        SuiteRunner(benchmark_runner=runner, concurrency=ConcurrencySettings(2)).run(agents())
    assert SuiteRunner(benchmark_runner=runner, concurrency=ConcurrencySettings(4)).run(agents(cases=1)).passed


def test_repeat_suite_has_new_case_runners_and_prepares_again():
    factory = Factory()
    suite = SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2))
    first, second = suite.run(agents()), suite.run(agents())
    assert first.suite_id != second.suite_id
    assert first.items[0].case_results[0].job_id != second.items[0].case_results[0].job_id
    assert factory.prepared == ["agent-0", "agent-0"]
    assert len(factory.created) == 6 and all(session.closed for session in factory.sessions)


def test_interrupt_during_second_submit_cancels_and_drains(monkeypatch):
    import agentbench.harness.scheduler as scheduler
    real = scheduler.ThreadPoolExecutor
    class InterruptedPool(real):
        count = 0
        def submit(self, *args, **kwargs):
            self.count += 1
            if self.count == 2:
                raise KeyboardInterrupt()
            return super().submit(*args, **kwargs)
    monkeypatch.setattr(scheduler, "ThreadPoolExecutor", InterruptedPool)
    def prepare(agent, control, callbacks):
        assert control.wait(3)
        control.check()
    with pytest.raises(KeyboardInterrupt):
        SuiteRunner(runner_factory=Factory(prepare=prepare), concurrency=ConcurrencySettings(2)).run(agents(2))
    assert not any(t.name.startswith("abb-case") for t in threading.enumerate())


def test_consumer_exception_cancels_workers_and_preserves_all_case_outcomes():
    def action(agent, case, control, callbacks, trace):
        from agentbench.harness.progress import BenchmarkProgress
        for _ in range(1500):
            control.check()
            callbacks["on_progress"](BenchmarkProgress("benchmark_execution", "started"))
        return result(agent, case.case_index)
    def consumer(event):
        if event["event"] == "progress" and event.get("agent_id"):
            raise OSError("disk unavailable")
    with pytest.raises(OSError, match="disk unavailable") as caught:
        SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(agents(cases=4), on_event=consumer)
    assert len(caught.value.partial_items[0].case_results) == 4
    assert not any(t.name.startswith("abb-case") for t in threading.enumerate())


def test_final_event_flush_failure_retains_completed_results():
    completed = []
    def tick():
        if completed:
            raise OSError("final flush failed")
    with pytest.raises(OSError, match="final flush failed") as caught:
        SuiteRunner(runner_factory=Factory(), concurrency=ConcurrencySettings(2)).run(
            agents(), on_agent_complete=completed.append, on_tick=tick)
    assert caught.value.partial_items[0].passed


def test_tick_interrupt_is_not_delivered_again_and_workers_are_reclaimed():
    ticks = 0
    factory = Factory()
    def tick():
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            # Bound the regression: repeating KeyboardInterrupt would deadlock.
            raise AssertionError("Interrupted consumer was invoked again")
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as caught:
        SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(agents(), on_tick=tick)
    assert ticks == 1
    assert len(caught.value.partial_items[0].case_results) == 2
    assert all(session.closed for session in factory.sessions)
    assert not any(t.name.startswith("abb-case") for t in threading.enumerate())


def test_queue_delivery_failure_preserves_every_prepared_case_identity():
    called = []
    factory = Factory(lambda *args: called.append(args))
    def consumer(event):
        if event["event"] == "case_queued":
            raise OSError("queue write failed")
    with pytest.raises(OSError, match="queue write failed") as caught:
        SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(
            agents(cases=3), on_event=consumer)
    assert not called
    cases = caught.value.partial_items[0].case_results
    assert [case.case_id for case in cases] == [f"agent-0-case-{index}" for index in range(3)]
    assert [case.status for case in cases] == ["skipped"] * 3


def test_fatal_runtime_error_cancels_sibling_and_marks_undispatched_cases():
    ready = threading.Barrier(2)
    def action(agent, case, control, *_):
        ready.wait(3)
        if case.case_index == 0:
            raise RuntimeInfrastructureError("cleanup failed")
        assert control.wait(3)
        control.check()
    with pytest.raises(RuntimeInfrastructureError) as caught:
        SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(agents(cases=3))
    assert [case.status for case in caught.value.partial_items[0].case_results] == ["failed", "cancelled", "skipped"]


def test_programmatic_cancel_returns_case_outcomes_and_skips_third_case():
    both = threading.Barrier(2)
    def action(agent, case, control, *_):
        both.wait(3)
        suite.cancel()
        control.check()
    suite = SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2))
    outcome = suite.run(agents(cases=3))
    assert [case.status for case in outcome.items[0].case_results] == ["cancelled", "cancelled", "skipped"]
    assert outcome.items[0].status == "cancelled"


def test_cancel_during_case_runner_creation_is_a_normal_cancellation():
    class CancelDuringCreate(Factory):
        def open_suite(self, suite_id, control):
            session = super().open_suite(suite_id, control)
            create = session.create
            def interrupted_create(agent, identity, sink):
                if identity.get("case_index") == 1:
                    control.cancel()
                    control.check()
                return create(agent, identity, sink)
            session.create = interrupted_create
            return session
    def action(agent, case, control, *_):
        assert control.wait(3)
        control.check()
    outcome = SuiteRunner(runner_factory=CancelDuringCreate(action), concurrency=ConcurrencySettings(2)).run(agents(cases=3))
    assert [case.status for case in outcome.items[0].case_results] == ["cancelled", "cancelled", "skipped"]


@pytest.mark.parametrize("workers", [1, 2])
def test_factory_cannot_reuse_preparation_runner_for_case_execution(workers):
    called = []
    class SharedFactory(Factory):
        def open_suite(self, suite_id, control):
            session = super().open_suite(suite_id, control)
            create = session.create
            shared = None
            def reused_create(agent, identity, sink):
                nonlocal shared
                if shared is None:
                    shared = create(agent, identity, sink)
                return shared
            session.create = reused_create
            return session
    factory = SharedFactory(lambda *args: called.append(args))
    with pytest.raises(SuiteConfigurationError, match="independent runner") as caught:
        SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(workers)).run(agents())
    assert not called
    assert len(caught.value.partial_items[0].case_results) == 2


def test_real_sigint_waits_for_cleanup_and_restores_handler():
    import os
    import signal
    before = signal.getsignal(signal.SIGINT)
    ready = threading.Barrier(2)
    def action(agent, case, control, *_):
        ready.wait(3)
        if case.case_index == 0:
            os.kill(os.getpid(), signal.SIGINT)
        assert control.wait(3)
        control.check()
    with pytest.raises(KeyboardInterrupt) as caught:
        SuiteRunner(runner_factory=Factory(action), concurrency=ConcurrencySettings(2)).run(agents(cases=3))
    assert len(caught.value.partial_items[0].case_results) == 3
    assert signal.getsignal(signal.SIGINT) is before
    assert not any(t.name.startswith("abb-case") for t in threading.enumerate())


def test_suite_close_does_not_mask_original_partial_results():
    class CloseFailureFactory(Factory):
        def open_suite(self, suite_id, control):
            session = super().open_suite(suite_id, control)
            def close():
                raise RuntimeInfrastructureError("additional close failure")
            session.close = close
            return session
    def action(agent, case, *_):
        raise RuntimeInfrastructureError("original runtime failure")
    with pytest.raises(RuntimeInfrastructureError, match="original runtime failure") as caught:
        SuiteRunner(runner_factory=CloseFailureFactory(action), concurrency=ConcurrencySettings(2)).run(agents())
    assert len(caught.value.partial_items[0].case_results) == 2
    assert str(caught.value.cleanup_error) == "additional close failure"


def test_preflight_all_agents_before_any_preparation():
    called = []
    def validate(agent):
        if agent.agent_id == "agent-1":
            raise ValueError("missing profile")
        return "test"
    factory = Factory(prepare=lambda *args: called.append(args), validate=validate)
    with pytest.raises(SuiteConfigurationError, match="missing profile"):
        SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(2)).run(agents(3))
    assert not called

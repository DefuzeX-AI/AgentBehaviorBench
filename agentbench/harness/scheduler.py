"""One bounded pool for preparation and Case execution, owned by a coordinator."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
import signal
import threading
import time
import heapq
from itertools import count
from types import MappingProxyType

from agentbench.runtime.contracts.execution import RunCancelled, RunControl
from agentbench.sdk.contracts import PreparedCase

from .errors import SuiteConfigurationError
from .events import EventBus
from .jobs import (CaseJob, CaseOutcome, PreparationJob, PreparationOutcome,
                   SuiteCallbacks, run_case_job, run_preparation_job)
from .result import CaseResult, EvaluationFailure, SuiteAgentResult
from .scheduling import AgentState, AgentSeed, RetryPolicy
from .scheduling.preparation import accept_preparation

CaseJobFactory = Callable[[PreparationJob, PreparedCase, Mapping[str, object]], CaseJob]


class CaseScheduler:
    """Workers return outcomes; only this coordinator mutates scheduling state."""

    def __init__(self, preparations: Sequence[PreparationJob], *, create_case_job: CaseJobFactory,
                 workers: int, control: RunControl, bus: EventBus,
                 callbacks: SuiteCallbacks, continue_on_error: bool,
                 retry_policy=None, seeds=None, retain_case=None):
        self.states = [AgentState(job) for job in preparations]
        self.unprepared, self.ready = deque(), deque()
        self.inflight: dict[Future, tuple[AgentState, PreparationJob | CaseJob]] = {}
        self.create_case_job = create_case_job
        self.workers = workers
        self.control, self.bus, self.callbacks = control, bus, callbacks
        self.continue_on_error = continue_on_error
        self.admission = True
        self.failure: BaseException | None = None
        self.consumer_failed = False
        self.interrupted = False
        self.retry_policy = retry_policy or RetryPolicy()
        self.retain_case = retain_case or (lambda _agent, case: case)
        self.delayed = []
        self._retry_order = count()
        for state in self.states:
            seed = (seeds or {}).get(state.preparation.registration.agent_id, AgentSeed())
            state.initialize(seed)
            now, monotonic_now = time.time(), time.monotonic()
            for case in tuple(state.pending):
                due = seed.retry_at.get(case.case_index)
                if due is not None and due > now:
                    state.pending.remove(case)
                    heapq.heappush(self.delayed, (monotonic_now + due - now, next(self._retry_order),
                                                  state, case.case_index))
            if state.pending:
                self.ready.append(state)
            missing = tuple(i for i in state.identities if i not in state.prepared and i not in state.results)
            if missing:
                state.preparation = replace(state.preparation, case_indices=missing)
                self.unprepared.append(state)

    def run(self) -> tuple[SuiteAgentResult, ...]:
        # Start the worker pool.
        pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="abb-case")
        previous_sigint = None
        if threading.current_thread() is threading.main_thread():
            previous_sigint = signal.getsignal(signal.SIGINT)
            # Record cancellation without throwing between submit and tracking.
            signal.signal(signal.SIGINT, self._interrupt)
        try:
            for state in self.states:
                self._finish_agent(state)
            while self.inflight or (self.admission and not self.control.cancelled
                                    and (self.ready or self.unprepared or self.delayed)):
                try:
                    self._release_retries()
                    self._fill_slots(pool)
                    if not self.inflight:
                        if not self.delayed:
                            break
                        self.bus.drain(discard=self.consumer_failed)
                        self.control.wait(min(0.1, max(0, self.delayed[0][0] - time.monotonic())))
                        continue
                    self.bus.drain(discard=self.consumer_failed)
                    done, _ = wait(self.inflight, timeout=0.1, return_when=FIRST_COMPLETED)
                    if done:
                        self.bus.drain_published(discard=self.consumer_failed)
                    for future in done:
                        state, job = self.inflight.pop(future)
                        try:
                            outcome = future.result()
                        except BaseException as exc:
                            outcome = self._unexpected_outcome(job, exc)
                        self._accept(state, job, outcome)
                except KeyboardInterrupt as exc:
                    self.consumer_failed = True
                    self.bus.fail(exc)
                    self._stop(exc)
                    self.interrupted = True
                except BaseException as exc:
                    self.consumer_failed = True
                    self.bus.fail(exc)
                    self._stop(exc)
            # At this point every dispatched task has returned, including its
            # Docker cleanup. Undispatched Cases receive explicit terminal rows.
            try:
                for state in self.states:
                    if state.started and not state.completed:
                        self._skip_remaining(state, "Cancelled before dispatch" if self.control.cancelled
                                             else "Suite stopped before dispatch")
                        self._finish_agent(state)
                self.bus.drain_published(discard=self.consumer_failed)
            except BaseException as exc:
                self._stop(exc)
        finally:
            try:
                pool.shutdown(wait=True, cancel_futures=True)
            finally:
                if previous_sigint is not None:
                    signal.signal(signal.SIGINT, previous_sigint)
        # Recovery remains complete even if a terminal-event consumer failed.
        for state in self.states:
            if state.started:
                self._skip_remaining(state, "Suite stopped before dispatch", emit=False)
        ordered = tuple(state.snapshot() for state in self.states if state.started)
        if self.interrupted:
            self.failure = KeyboardInterrupt()
        if self.failure is not None:
            self.failure.partial_items = ordered
            raise self.failure
        return ordered

    def _interrupt(self, signum, frame):
        self.interrupted = True
        self.admission = False
        self.control.force_cancel() if self.control.cancelled else self.control.cancel()

    def _stop(self, error: BaseException):
        self.failure = self.failure or error
        self.admission = False
        self.control.cancel()

    def _publish(self, event, callback=None, args=()):
        if not self.consumer_failed:
            self.bus.publish(event, callback, args)

    # Queue work for the worker pool.
    def _fill_slots(self, pool: ThreadPoolExecutor):
        while self.admission and not self.control.cancelled and len(self.inflight) < self.workers:
            if self.ready:
                state = self.ready.popleft()
                case = state.pending.popleft()
                if state.pending:
                    self.ready.append(state)
                identity = state.begin_attempt(case)
                try:
                    job = self.create_case_job(state.preparation, case, identity)
                    if case.case_index in state.recoveries:
                        job = replace(job, previous_result=state.recoveries.pop(case.case_index))
                    self._publish({**identity, 'event': 'attempt_dispatched'})
                except BaseException as exc:
                    failure = exc if isinstance(exc, (RunCancelled, KeyboardInterrupt)) else SuiteConfigurationError(str(exc))
                    previous = state.waiting_results.get(case.case_index)
                    result = previous or CaseResult(state.preparation.registration.agent_id, case.case_index,
                                        str(identity["job_id"]),
                                        "cancelled" if isinstance(exc, RunCancelled) else "failed",
                                        case_id=case.case_id, error_type=type(exc).__name__, error_message=str(exc),
                                        attempt_id=identity['attempt_id'], attempt_number=identity['attempt_number'])
                    state.results[case.case_index] = result
                    if isinstance(exc, RunCancelled) and self.control.cancelled:
                        self.admission = False
                    else:
                        self._stop(failure)
                    self._publish_case(state, result)
                    if previous is not None:
                        self._publish({**identity, 'event': 'case_retry_cancelled', 'status': 'cancelled'})
                    continue
                function = run_case_job

            # Prepare Cases for an Agent that does not have them yet.
            elif self.unprepared:
                state = self.unprepared.popleft()
                job = state.preparation
                
                function = run_preparation_job
            else:
                break

            # Queue work for the worker pool.
            try:
                future = pool.submit(function, job, control=self.control, bus=self.bus, callbacks=self.callbacks)
            except BaseException as exc:
                state.started = True
                previous = state.waiting_results.get(job.case.case_index) if isinstance(job, CaseJob) else None
                self._accept(state, job, CaseOutcome(previous, fatal=exc) if previous
                             else self._unexpected_outcome(job, exc))
                if isinstance(exc, KeyboardInterrupt):
                    self.interrupted = True
                continue
            if isinstance(job, CaseJob):
                state.waiting_results.pop(job.case.case_index, None)
            state.started = True
            self.inflight[future] = (state, job)

    def _accept(self, state: AgentState, job: PreparationJob | CaseJob,
                outcome: PreparationOutcome | CaseOutcome):
        if outcome.fatal is not None:
            self._stop(outcome.fatal)
        if isinstance(outcome, PreparationOutcome):
            accept_preparation(self, state, job, outcome)
        else:
            result = outcome.result
            retries = state.retries.get(result.case_index, 0)
            if (outcome.fatal is None and self.admission and self.continue_on_error
                    and self.retry_policy.permits(result, retries)):
                recovery = (result.artifacts or {})['recovery']
                if recovery['action'] != 'resume_request' or callable(getattr(job.runner, 'recover_case', None)):
                    self._queue_retry(state, result)
                    return
            state.results[result.case_index] = result
            if result.status != "succeeded" and not self.continue_on_error:
                self.admission = False
            self._publish_case(state, result)
        self._finish_agent(state)

    def _queue_retry(self, state, result):
        index = result.case_index
        state.waiting_results[index] = result
        state.retries[index] = state.retries.get(index, 0) + 1
        delay = self.retry_policy.delay(state.retries[index])
        if (result.artifacts or {})['recovery']['action'] == 'resume_request':
            state.recoveries[index] = result
        self._publish({**state.identities[index], 'event': 'case_attempt_failed',
                       'status': 'failed', 'case_result': result})
        self._publish({**state.identities[index], 'event': 'retry_scheduled', 'status': 'retry_wait',
                       'retry_count': state.retries[index], 'retry_at': time.time() + delay,
                       'recovery_action': (result.artifacts or {})['recovery']['action']})
        heapq.heappush(self.delayed, (time.monotonic() + delay, next(self._retry_order), state, index))

    def _release_retries(self):
        while self.delayed and self.delayed[0][0] <= time.monotonic() and self.admission and not self.control.cancelled:
            _, _, state, index = heapq.heappop(self.delayed)
            state.pending.append(state.prepared[index])
            if state not in self.ready:
                self.ready.append(state)

    def _publish_case(self, state: AgentState, result: CaseResult):
        phase = 'generate' if (result.artifacts or {}).get('phase') == 'case_generation' else 'execute'
        self._publish({**state.identities[result.case_index], "event": "case_completed",
                       "status": result.status, 'phase': phase, "case_result": result})

    def _finish_agent(self, state: AgentState):
        if state.completed or len(state.results) != state.preparation.registration.case_count:
            return
        state.completed = True
        item = state.snapshot()
        identity = state.preparation.identity
        self._publish({**identity, "phase": None, "event": "agent_completed", "status": item.status, "item": item},
                      self.callbacks.on_agent_complete, (item,))

    def _skip_remaining(self, state: AgentState, reason: str, *, emit=True):
        for index, identity in state.identities.items():
            if index in state.results:
                continue
            previous = state.waiting_results.get(index)
            result = previous or CaseResult(state.preparation.registration.agent_id, index, str(identity["job_id"]),
                                           "skipped", case_id=identity["case_id"],
                                           error_type="CaseSkipped", error_message=reason)
            state.results[index] = result
            if emit:
                self._publish_case(state, result)
                if previous is not None:
                    self._publish({**identity, 'event': 'case_retry_cancelled', 'status': 'cancelled'})
        state.pending.clear()

    @staticmethod
    def _unexpected_outcome(job: PreparationJob | CaseJob, exc: BaseException):
        if isinstance(job, PreparationJob):
            return PreparationOutcome(error=EvaluationFailure(type(exc).__name__, str(exc)), fatal=exc)
        return CaseOutcome(CaseResult(
            job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]), "failed",
            case_id=job.case.case_id, error_type=type(exc).__name__, error_message=str(exc)), fatal=exc)

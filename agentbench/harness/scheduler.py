"""One bounded pool for preparation and Case execution, owned by a coordinator."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
import signal
import threading
from types import MappingProxyType
from uuid import uuid4

from agentbench.runtime.contracts.execution import RunCancelled, RunControl
from agentbench.sdk.contracts import PreparedCase

from .errors import SuiteConfigurationError
from .events import EventBus
from .jobs import (CaseJob, CaseOutcome, PreparationJob, PreparationOutcome,
                   SuiteCallbacks, run_case_job, run_preparation_job)
from .result import CaseResult, EvaluationFailure, SuiteAgentResult

CaseJobFactory = Callable[[PreparationJob, PreparedCase, Mapping[str, object]], CaseJob]


@dataclass
class _AgentState:
    preparation: PreparationJob
    started: bool = False
    completed: bool = False
    preparation_error: EvaluationFailure | None = None
    pending: deque[PreparedCase] = field(default_factory=deque)
    results: dict[int, CaseResult] = field(default_factory=dict)
    identities: dict[int, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self):
        parent = self.preparation.identity
        self.identities = {
            index: MappingProxyType({**parent, "job_id": f"case_{uuid4().hex}",
                                     "agent_job_id": parent["job_id"], "phase": "execute",
                                     "case_index": index, "case_id": None})
            for index in range(self.preparation.registration.case_count)
        }

    def snapshot(self) -> SuiteAgentResult:
        return SuiteAgentResult(
            self.preparation.registration.agent_id,
            tuple(self.results[index] for index in sorted(self.results)),
            self.preparation.registration.case_count, self.preparation_error,
        )


class CaseScheduler:
    """Workers return outcomes; only this coordinator mutates scheduling state."""

    def __init__(self, preparations: Sequence[PreparationJob], *, create_case_job: CaseJobFactory,
                 workers: int, control: RunControl, bus: EventBus,
                 callbacks: SuiteCallbacks, continue_on_error: bool):
        self.states = [_AgentState(job) for job in preparations]
        self.unprepared = deque(self.states)
        self.ready: deque[_AgentState] = deque()
        self.inflight: dict[Future, tuple[_AgentState, PreparationJob | CaseJob]] = {}
        self.create_case_job = create_case_job
        self.workers = workers
        self.control, self.bus, self.callbacks = control, bus, callbacks
        self.continue_on_error = continue_on_error
        self.admission = True
        self.failure: BaseException | None = None
        self.consumer_failed = False
        self.interrupted = False

    def run(self) -> tuple[SuiteAgentResult, ...]:
        # 开线程池
        pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="abb-case")
        previous_sigint = None
        if threading.current_thread() is threading.main_thread():
            previous_sigint = signal.getsignal(signal.SIGINT)
            # Record cancellation without throwing between submit and tracking.
            signal.signal(signal.SIGINT, self._interrupt)
        try:
            while self.inflight or (self.admission and not self.control.cancelled
                                    and (self.ready or self.unprepared)):
                try:
                    self._fill_slots(pool)
                    if not self.inflight:
                        break
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

    # 线程排队操作
    def _fill_slots(self, pool: ThreadPoolExecutor):
        while self.admission and not self.control.cancelled and len(self.inflight) < self.workers:
            if self.ready:
                state = self.ready.popleft()
                case = state.pending.popleft()
                if state.pending:
                    self.ready.append(state)
                identity = state.identities[case.case_index]
                try:
                    job = self.create_case_job(state.preparation, case, identity)
                except BaseException as exc:
                    failure = exc if isinstance(exc, (RunCancelled, KeyboardInterrupt)) else SuiteConfigurationError(str(exc))
                    result = CaseResult(state.preparation.registration.agent_id, case.case_index,
                                        str(identity["job_id"]),
                                        "cancelled" if isinstance(exc, RunCancelled) else "failed",
                                        case_id=case.case_id, error_type=type(exc).__name__, error_message=str(exc))
                    state.results[case.case_index] = result
                    if isinstance(exc, RunCancelled) and self.control.cancelled:
                        self.admission = False
                    else:
                        self._stop(failure)
                    self._publish_case(state, result)
                    continue
                function = run_case_job

            # 遇到尚未准备 Cases 的 Agent 做出以下事情
            elif self.unprepared:
                state = self.unprepared.popleft()
                job = state.preparation
                
                function = run_preparation_job
            else:
                break

            # 线程排队操作
            try:
                future = pool.submit(function, job, control=self.control, bus=self.bus, callbacks=self.callbacks)
            except BaseException as exc:
                state.started = True
                self._accept(state, job, self._unexpected_outcome(job, exc))
                if isinstance(exc, KeyboardInterrupt):
                    self.interrupted = True
                continue
            state.started = True
            self.inflight[future] = (state, job)

    def _accept(self, state: _AgentState, job: PreparationJob | CaseJob,
                outcome: PreparationOutcome | CaseOutcome):
        if outcome.fatal is not None:
            self._stop(outcome.fatal)
        if isinstance(outcome, PreparationOutcome):
            if outcome.error is not None:
                state.preparation_error = outcome.error
                if not self.continue_on_error:
                    self.admission = False
                self._skip_remaining(state, "Case batch preparation failed")
            else:
                state.pending.extend(outcome.cases)
                if state.pending:
                    self.ready.append(state)
                for case in outcome.cases:
                    identity = MappingProxyType({**state.identities[case.case_index], "case_id": case.case_id})
                    state.identities[case.case_index] = identity
                # Preserve every prepared identity before a consumer can fail.
                for case in outcome.cases:
                    identity = state.identities[case.case_index]
                    self._publish({**identity, "event": "case_queued", "status": "queued"})
        else:
            result = outcome.result
            state.results[result.case_index] = result
            if result.status != "succeeded" and not self.continue_on_error:
                self.admission = False
            self._publish_case(state, result)
        self._finish_agent(state)

    def _publish_case(self, state: _AgentState, result: CaseResult):
        self._publish({**state.identities[result.case_index], "event": "case_completed",
                       "status": result.status, "case_result": result})

    def _finish_agent(self, state: _AgentState):
        if state.completed or len(state.results) != state.preparation.registration.case_count:
            return
        state.completed = True
        item = state.snapshot()
        identity = state.preparation.identity
        self._publish({**identity, "phase": None, "event": "agent_completed", "status": item.status, "item": item},
                      self.callbacks.on_agent_complete, (item,))

    def _skip_remaining(self, state: _AgentState, reason: str, *, emit=True):
        for index, identity in state.identities.items():
            if index in state.results:
                continue
            result = CaseResult(state.preparation.registration.agent_id, index, str(identity["job_id"]),
                                "skipped", case_id=identity["case_id"],
                                error_type="CaseSkipped", error_message=reason)
            state.results[index] = result
            if emit:
                self._publish_case(state, result)
        state.pending.clear()

    @staticmethod
    def _unexpected_outcome(job: PreparationJob | CaseJob, exc: BaseException):
        if isinstance(job, PreparationJob):
            return PreparationOutcome(error=EvaluationFailure(type(exc).__name__, str(exc)), fatal=exc)
        return CaseOutcome(CaseResult(
            job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]), "failed",
            case_id=job.case.case_id, error_type=type(exc).__name__, error_message=str(exc)), fatal=exc)

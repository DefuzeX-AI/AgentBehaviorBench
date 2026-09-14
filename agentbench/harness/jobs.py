"""Independent batch preparation and single-Case worker tasks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace

from agentbench.runtime.contracts.execution import RunCancelled, RunControl, RuntimeInfrastructureError
from agentbench.sdk.contracts import EvaluationRunner, PreparedCase

from .errors import ProviderSelectionError, SuiteConfigurationError
from .events import EventBus, EventDeliveryError
from .progress import BenchmarkProgress, ProgressCallback
from .registry import AgentRegistration
from .result import CaseResult, EvaluationFailure, SuiteAgentResult


@dataclass(frozen=True)
class SuiteCallbacks:
    total: int
    on_agent_start: Callable[[AgentRegistration, int, int], None] | None = None
    on_agent_complete: Callable[[SuiteAgentResult], None] | None = None
    on_progress: ProgressCallback | None = None
    on_step_start: Callable | None = None
    on_step_complete: Callable | None = None
    on_step_failure: Callable | None = None


@dataclass(frozen=True)
class PreparationJob:
    registration: AgentRegistration
    runner: EvaluationRunner
    identity: Mapping[str, object]


@dataclass(frozen=True)
class CaseJob:
    registration: AgentRegistration
    runner: EvaluationRunner
    case: PreparedCase
    identity: Mapping[str, object]


@dataclass(frozen=True)
class PreparationOutcome:
    cases: tuple[PreparedCase, ...] = ()
    error: EvaluationFailure | None = None
    fatal: BaseException | None = None


@dataclass(frozen=True)
class CaseOutcome:
    result: CaseResult
    fatal: BaseException | None = None


def fatal_error(exc: BaseException, control: RunControl) -> BaseException | None:
    if isinstance(exc, ProviderSelectionError):
        return SuiteConfigurationError(str(exc))
    if isinstance(exc, (RuntimeInfrastructureError, EventDeliveryError)) or not isinstance(exc, Exception):
        return exc
    if isinstance(exc, RunCancelled) and not control.cancelled:
        return exc
    return None


class JobEvents:
    """Own one task's routing identity and changing artifact context."""

    def __init__(self, bus: EventBus, identity: Mapping[str, object], callbacks: SuiteCallbacks):
        self.bus = bus
        self.identity = dict(identity)
        self.scope = dict(identity)
        self.callbacks = callbacks

    def progress(self, event: BenchmarkProgress) -> None:
        inherited = {key: self.scope[key] for key in
                     ("artifact_run_id", "sdk_run_id", "event_timing")
                     if getattr(event, key) is None and key in self.scope}
        enriched = replace(event, **inherited, **self.identity)
        data = asdict(enriched)
        self.scope.update({key: value for key, value in data.items() if value is not None})
        self.bus.publish({**self.scope, **data, "event": "progress"},
                         self.callbacks.on_progress, (enriched,))

    def step_started(self, agent_id, input_id, payload) -> None:
        self.bus.publish({**self.scope, "event": "step_started", "input_id": input_id, "payload": payload},
                         self.callbacks.on_step_start, (self.identity["agent_id"], input_id, payload))

    def step_completed(self, agent_id, step) -> None:
        self.bus.publish({**self.scope, "event": "step_completed", "step": step},
                         self.callbacks.on_step_complete, (self.identity["agent_id"], step))

    def step_failed(self, agent_id, failure) -> None:
        self.bus.publish({**self.scope, "event": "step_failed", "failure": failure},
                         self.callbacks.on_step_failure, (self.identity["agent_id"], failure))


def run_preparation_job(job: PreparationJob, *, control: RunControl,
                        bus: EventBus, callbacks: SuiteCallbacks) -> PreparationOutcome:
    events = JobEvents(bus, job.identity, callbacks)
    try:
        control.check()
        bus.publish({**job.identity, "event": "agent_started", "status": "running"},
                    callbacks.on_agent_start,
                    (job.registration, job.identity["registration_index"] + 1, callbacks.total))


        # 在这里 我们真正的开始调用 createcases 来创建 case（可以去看kuma 的 create_cases 方法）
        cases = tuple(job.runner.prepare_cases(job.registration, on_progress=events.progress))


        
        if len(cases) != job.registration.case_count:
            raise ValueError("Prepared Case count does not match the requested count")
        if not all(isinstance(case, PreparedCase) for case in cases):
            raise TypeError("prepare_cases must return PreparedCase descriptors")
        if tuple(case.case_index for case in cases) != tuple(range(len(cases))):
            raise ValueError("Prepared Cases must have consecutive ordered indices")
        identifiers = [case.case_id for case in cases if case.case_id is not None]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Prepared Cases contain duplicate IDs")
        return PreparationOutcome(cases=cases)
    except BaseException as exc:
        return PreparationOutcome(error=EvaluationFailure(type(exc).__name__, str(exc), getattr(exc, 'artifacts', None)),
                                  fatal=fatal_error(exc, control))


def run_case_job(job: CaseJob, *, control: RunControl,
                 bus: EventBus, callbacks: SuiteCallbacks) -> CaseOutcome:
    events = JobEvents(bus, job.identity, callbacks)
    try:
        control.check()
        bus.publish({**job.identity, "event": "case_started", "status": "running"})
        benchmark = job.runner.run_case(
            job.registration, job.case, on_progress=events.progress,
            on_step_start=events.step_started, on_step_complete=events.step_completed,
            on_step_failure=events.step_failed,
        )
        result = CaseResult(job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]),
                            "succeeded" if benchmark.passed else "failed",
                            case_id=job.case.case_id, benchmark=benchmark)
        return CaseOutcome(result)
    except BaseException as exc:
        result = CaseResult(job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]),
                            "cancelled" if isinstance(exc, RunCancelled) else "failed",
                            case_id=job.case.case_id, error_type=type(exc).__name__, error_message=str(exc),
                            artifacts=getattr(exc, 'artifacts', None))
        return CaseOutcome(result, fatal_error(exc, control))

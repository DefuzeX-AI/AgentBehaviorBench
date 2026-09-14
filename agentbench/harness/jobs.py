"""Independent batch preparation and single-Case worker tasks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace

from agentbench.runtime.contracts.execution import RunCancelled, RunControl, RuntimeInfrastructureError
from agentbench.sdk.contracts import EvaluationRunner, PreparedCase, PreparedCaseBatch, PreparationFailure

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
    case_indices: tuple[int, ...] | None = None


@dataclass(frozen=True)
class CaseJob:
    registration: AgentRegistration
    runner: EvaluationRunner
    case: PreparedCase
    identity: Mapping[str, object]
    previous_result: CaseResult | None = None


@dataclass(frozen=True)
class PreparationOutcome:
    cases: tuple[PreparedCase, ...] = ()
    error: EvaluationFailure | None = None
    fatal: BaseException | None = None
    failures: tuple[PreparationFailure, ...] = ()
    unattempted_indices: tuple[int, ...] = ()


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
        partial = getattr(job.runner, 'prepare_case_batch', None)
        requested = tuple(range(job.registration.case_count)) if job.case_indices is None else job.case_indices
        if callable(partial):
            batch = partial(job.registration, case_indices=requested, on_progress=events.progress)
            if not isinstance(batch, PreparedCaseBatch):
                raise TypeError('prepare_case_batch must return PreparedCaseBatch')
            cases = batch.cases
        else:
            if requested != tuple(range(job.registration.case_count)):
                raise ValueError('This SDK cannot prepare a partial Case selection')
            cases = tuple(job.runner.prepare_cases(job.registration, on_progress=events.progress))
            batch = None


        
        if batch is None and len(cases) != job.registration.case_count:
            raise ValueError("Prepared Case count does not match the requested count")
        if not all(isinstance(case, PreparedCase) for case in cases):
            raise TypeError("prepare_cases must return PreparedCase descriptors")
        indices = tuple(case.case_index for case in cases)
        if indices != tuple(sorted(set(indices))) or not set(indices).issubset(requested):
            raise ValueError("Prepared Cases must retain distinct requested indices")
        identifiers = [case.case_id for case in cases if case.case_id is not None]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Prepared Cases contain duplicate IDs")
        if batch is not None:
            covered = set(indices) | {failure.case_index for failure in batch.failures} | set(batch.unattempted_indices)
            if covered != set(requested):
                raise ValueError('Partial preparation must account for every requested Case')
        return PreparationOutcome(cases=cases, failures=() if batch is None else batch.failures,
                                  unattempted_indices=() if batch is None else batch.unattempted_indices)
    except BaseException as exc:
        return PreparationOutcome(error=EvaluationFailure(type(exc).__name__, str(exc), getattr(exc, 'artifacts', None)),
                                  fatal=fatal_error(exc, control))


def run_case_job(job: CaseJob, *, control: RunControl,
                 bus: EventBus, callbacks: SuiteCallbacks) -> CaseOutcome:
    events = JobEvents(bus, job.identity, callbacks)
    try:
        control.check()
        status = 'retrying' if job.identity.get('attempt_number', 1) > 1 or job.previous_result else 'running'
        bus.publish({**job.identity, "event": "case_started", "status": status})
        execute = job.runner.run_case if job.previous_result is None else getattr(job.runner, 'recover_case')
        recovery = {} if job.previous_result is None else {'previous_result': job.previous_result}
        benchmark = execute(
            job.registration, job.case, **recovery, on_progress=events.progress,
            on_step_start=events.step_started, on_step_complete=events.step_completed,
            on_step_failure=events.step_failed,
        )
        result = CaseResult(job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]),
                            "succeeded" if benchmark.passed else "failed",
                            case_id=job.case.case_id, benchmark=benchmark)
        return CaseOutcome(replace(result, attempt_id=job.identity.get('attempt_id'),
                                   attempt_number=job.identity.get('attempt_number', 1)))
    except BaseException as exc:
        result = CaseResult(job.registration.agent_id, job.case.case_index, str(job.identity["job_id"]),
                            "cancelled" if isinstance(exc, RunCancelled) else "failed",
                            case_id=job.case.case_id, error_type=type(exc).__name__, error_message=str(exc),
                            artifacts=getattr(exc, 'artifacts', None))
        artifacts = dict(job.previous_result.artifacts or {}) if job.previous_result is not None else {}
        artifacts.update(result.artifacts or {})
        if isinstance(getattr(exc, 'recovery', None), Mapping):
            artifacts['recovery'] = dict(exc.recovery)
        return CaseOutcome(replace(result, artifacts=artifacts or None,
                                   attempt_id=job.identity.get('attempt_id'),
                                   attempt_number=job.identity.get('attempt_number', 1)), fatal_error(exc, control))

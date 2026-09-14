"""Provider-independent interfaces implemented by evaluation SDK adapters.

This module uses only the standard library. Importing a contract must never
import an evaluator, discover plugins, or require an evaluator's dependencies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentbench.harness.registry import AgentRegistration
    from agentbench.harness.result import BenchmarkResult
    from agentbench.runtime.contracts.execution import RunControl
    from agentbench.runtime.docker.build_coordinator import BuildCoordinator
    from agentbench.runtime.services import RuntimeServices


@dataclass(frozen=True, slots=True)
class SDKReference:
    """Identity of an SDK, without importing or initializing its implementation.

    For discovered adapters, ``name`` is the directory name and ``object_ref``
    is the qualified ``plugin`` export. Python injection is an explicit caller
    override, not an additional source of discoverable adapters.
    """

    name: str
    source: Literal["directory", "python"]
    object_ref: str


class SDKReport(Protocol):
    status: str
    confidence: object
    issues: tuple[object, ...]
    evidence_gaps: tuple[object, ...]


class SDKTestInput(Protocol):
    input_id: str
    payload: object


class SDKRun(Protocol):
    """One Case: deliver an Input, submit once, then advance or expose a report.

    History entries belong to the adapter; the host runner only counts them.
    No KUMA state objects, submission extensions, or private fields are required.
    """

    run_id: str
    state: str
    report: SDKReport | None
    history: tuple[object, ...]

    def get_input(self, *, full: bool = False) -> SDKTestInput | None: ...

    def submit(
        self, output: object = None, *, status: str = "completed",
        error: str | None = None,
    ) -> SDKReport | None: ...


class SDKRunFactory(Protocol):
    def __call__(self, **kwargs: object) -> SDKRun: ...


class SDK(Protocol):
    """A module or configured object receiving repo_path plus its own options."""

    def create_run(self, **kwargs: object) -> SDKRun: ...


@dataclass(frozen=True, slots=True)
class PreparedCase:
    """Immutable work description passed from preparation to one Case runner."""

    case_index: int
    case_id: str | None = None
    artifact_path: Path | None = None
    content_sha256: str | None = None
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.case_index) is not int or self.case_index < 0:
            raise ValueError('case_index must be a non-negative integer')
        if self.case_id is not None and (not isinstance(self.case_id, str) or not self.case_id.strip()):
            raise ValueError('case_id must be a non-empty string when provided')
        if self.artifact_path is not None and not isinstance(self.artifact_path, Path):
            raise TypeError('artifact_path must be a pathlib.Path when provided')
        if self.artifact_path is not None and not self.artifact_path.is_absolute():
            raise ValueError('artifact_path must be absolute when provided')
        for name in ('content_sha256', 'artifact_sha256'):
            digest = getattr(self, name)
            if digest is not None and (
                not isinstance(digest, str) or len(digest) != 64
                or any(character not in '0123456789abcdef' for character in digest)
            ):
                raise ValueError(f'{name} must be a lowercase SHA-256 digest')


@dataclass(frozen=True, slots=True)
class PreparationFailure:
    """One logical Case slot that could not produce a reusable Case.

    SDK error fields retain their original meaning: ``retryable`` alone is not
    permission to start another paid request. Request identities and artifacts
    allow the coordinator to choose recovery without interpreting error text.
    """

    case_index: int
    error_type: str
    error_message: str
    phase: str = 'case_generation'
    code: str | None = None
    retryable: bool | None = None
    client_request_id: str | None = None
    request_id: str | None = None
    artifacts: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if type(self.case_index) is not int or self.case_index < 0:
            raise ValueError('case_index must be a non-negative integer')
        if self.retryable is not None and type(self.retryable) is not bool:
            raise TypeError('retryable must be a boolean when provided')


@dataclass(frozen=True, slots=True)
class PreparedCaseBatch:
    """Partial preparation results retaining the original, disjoint slot IDs."""

    cases: tuple[PreparedCase, ...]
    failures: tuple[PreparationFailure, ...] = ()
    unattempted_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        indices = [case.case_index for case in self.cases]
        indices.extend(failure.case_index for failure in self.failures)
        indices.extend(self.unattempted_indices)
        if any(type(index) is not int or index < 0 for index in indices):
            raise ValueError('Batch indices must be non-negative integers')
        if len(indices) != len(set(indices)):
            raise ValueError('Prepared, failed and unattempted Case indices must be disjoint')

    @property
    def failures_by_index(self) -> dict[int, PreparationFailure]:
        return {failure.case_index: failure for failure in self.failures}


@runtime_checkable
class PartialCasePreparation(Protocol):
    """Optional capability; legacy runners may keep all-or-nothing preparation."""

    def prepare_case_batch(
        self, registration: AgentRegistration, *,
        case_indices: tuple[int, ...] | None = None, on_progress=None,
    ) -> PreparedCaseBatch: ...


class EvaluationRunner(Protocol):
    """Prepare explicit Cases, then execute one Case in an isolated runner."""

    def validate_sdk(self, registration: AgentRegistration) -> str: ...

    def prepare_cases(
        self, registration: AgentRegistration, *, on_progress=None,
    ) -> tuple[PreparedCase, ...]: ...

    def run_case(
        self, registration: AgentRegistration, case: PreparedCase, *,
        on_progress=None, on_step_start=None, on_step_complete=None, on_step_failure=None,
    ) -> BenchmarkResult: ...


@dataclass(frozen=True, slots=True)
class RunnerConcurrencyCapabilities:
    """Optional plugin promise for isolated Case execution and cancellation."""

    isolated_cases: bool = False
    cooperative_cancel: bool = False


@dataclass(frozen=True, slots=True)
class RunnerRecoveryCapabilities:
    """Recovery promises, independent of concurrent execution support.

    ``safe_case_replay`` requires an audited Agent declaration: new isolated
    sessions alone do not make external side effects safe to repeat.
    """

    safe_case_replay: bool = False
    resume_judgment: bool = False


@dataclass(frozen=True, slots=True)
class SDKRunnerContext:
    """Host facilities available to a plugin's runner factory."""

    environ: Mapping[str, str]
    model: str | None
    trace_sink: object
    trace_max_bytes: int
    control: RunControl | None = None
    build_coordinator: BuildCoordinator | None = None
    job_context: Mapping[str, object] | None = None
    runtime_services: RuntimeServices | None = None


@runtime_checkable
class EvaluationSDKPlugin(Protocol):
    """Directory adapter owning an SDK's dependencies and execution loop.

    Export an instance as ``plugin`` from ``sdk/plugin/<name>/plugin.py``. The directory
    supplies its name; no duplicate registration or name field is required.
    Importing the entry module must not start work or require SDK dependencies.
    """

    execution: Literal["container", "local"]

    def create_benchmark_runner(
        self, *, context: SDKRunnerContext, options: Mapping[str, object],
    ) -> EvaluationRunner: ...

"""Framework-neutral results produced by the benchmark harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agentbench.adapter import AdapterInvocation

from agentbench.sdk.contracts import SDKReport


@dataclass(frozen=True)
class BenchmarkStepResult:
    """One SDK Input and the corresponding Agent invocation."""

    input_id: str
    payload: object
    invocation: AdapterInvocation


@dataclass(frozen=True)
class BenchmarkStepFailure:
    """One SDK Input that failed before the full step completed."""

    input_id: str
    payload: object
    error_type: str
    error_message: str
    output: object | None = None
    raw_output: object | None = None


@dataclass(frozen=True)
class BenchmarkResult:
    """Validated SDK output for one Case of a registered Agent."""

    agent_id: str
    adapter_name: str
    run_id: str
    run_state: str
    report: SDKReport | None
    steps: tuple[BenchmarkStepResult, ...]
    history_count: int
    provider_mode: str | None = None

    @property
    def passed(self) -> bool:
        return self.report is not None and self.report.status == "pass"


CaseStatus = Literal["succeeded", "failed", "cancelled", "skipped"]


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    error_type: str
    error_message: str
    artifacts: dict | None = None


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One Case's terminal outcome, including Cases never dispatched."""

    agent_id: str
    case_index: int
    job_id: str
    status: CaseStatus
    case_id: str | None = None
    benchmark: BenchmarkResult | None = None
    error_type: str | None = None
    error_message: str | None = None
    artifacts: dict | None = None

    def __post_init__(self) -> None:
        if type(self.case_index) is not int or self.case_index < 0:
            raise ValueError("Case index must be a nonnegative integer")
        if self.status not in {"succeeded", "failed", "cancelled", "skipped"}:
            raise ValueError("Case result requires a terminal status")
        if self.benchmark is not None and self.benchmark.agent_id != self.agent_id:
            raise ValueError("Case benchmark belongs to another Agent")
        if self.status == "succeeded" and (self.benchmark is None or not self.benchmark.passed):
            raise ValueError("A succeeded Case requires a passing benchmark")
        if self.status in {"cancelled", "skipped"} and self.benchmark is not None:
            raise ValueError("Unfinished Cases cannot carry a completed benchmark")
        if (self.error_type is None) != (self.error_message is None):
            raise ValueError("Case error type and message must be supplied together")


@dataclass(frozen=True)
class SuiteAgentResult:
    """Agent aggregate derived from ordered Case outcomes and batch preparation."""

    agent_id: str
    case_results: tuple[CaseResult, ...] = ()
    requested_case_count: int = 1
    preparation_error: EvaluationFailure | None = None

    def __post_init__(self) -> None:
        if type(self.requested_case_count) is not int or self.requested_case_count < 1:
            raise ValueError("Suite Agent requested case count must be positive")
        if not self.case_results and self.preparation_error is None:
            raise ValueError("Suite Agent result requires Case outcomes or a preparation error")
        indices = tuple(case.case_index for case in self.case_results)
        if indices != tuple(sorted(set(indices))) or any(i >= self.requested_case_count for i in indices):
            raise ValueError("Case results must have distinct ordered indices within the requested count")
        if any(case.agent_id != self.agent_id for case in self.case_results):
            raise ValueError("Suite Agent ID does not match its Case results")

    @property
    def benchmarks(self) -> tuple[BenchmarkResult, ...]:
        return tuple(case.benchmark for case in self.case_results if case.benchmark is not None)

    @property
    def completed_case_count(self) -> int:
        return len(self.benchmarks)

    @property
    def attempted_case_count(self) -> int:
        return sum(case.status != "skipped" for case in self.case_results)

    @property
    def skipped_case_count(self) -> int:
        return self.requested_case_count - self.attempted_case_count

    @property
    def error_type(self) -> str | None:
        return (self.preparation_error.error_type if self.preparation_error else
                next((case.error_type for case in self.case_results if case.error_type), None))

    @property
    def error_message(self) -> str | None:
        return (self.preparation_error.error_message if self.preparation_error else
                next((case.error_message for case in self.case_results if case.error_type), None))

    @property
    def passed(self) -> bool:
        return (self.preparation_error is None and len(self.case_results) == self.requested_case_count
                and all(case.status == "succeeded" for case in self.case_results))

    @property
    def status(self) -> CaseStatus:
        if self.passed:
            return "succeeded"
        if self.preparation_error is not None:
            return "cancelled" if self.preparation_error.error_type == "RunCancelled" else "failed"
        if any(case.status == "failed" for case in self.case_results):
            return "failed"
        if any(case.status == "cancelled" for case in self.case_results):
            return "cancelled"
        return "skipped"


@dataclass(frozen=True)
class BenchmarkSuiteResult:
    """Aggregate result for a selected set of benchmark Agents."""

    suite_id: str
    selected_agent_ids: tuple[str, ...]
    items: tuple[SuiteAgentResult, ...]

    def __post_init__(self) -> None:
        if not self.suite_id.strip():
            raise ValueError("A benchmark suite result requires a Suite ID")
        if not self.selected_agent_ids:
            raise ValueError("A benchmark suite result requires selected Agents")
        attempted_ids = tuple(item.agent_id for item in self.items)
        if attempted_ids != self.selected_agent_ids[: len(attempted_ids)]:
            raise ValueError("Suite result items must follow the selected Agent order")

    @property
    def selected_count(self) -> int:
        return len(self.selected_agent_ids)

    @property
    def attempted_count(self) -> int:
        return len(self.items)

    @property
    def passed_count(self) -> int:
        return sum(item.passed for item in self.items)

    @property
    def failed_count(self) -> int:
        return self.attempted_count - self.passed_count

    @property
    def skipped_count(self) -> int:
        return self.selected_count - self.attempted_count

    @property
    def passed(self) -> bool:
        return self.skipped_count == 0 and self.failed_count == 0

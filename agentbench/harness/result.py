"""Framework-neutral results produced by the benchmark harness."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
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
    evidence_status: str = "unknown"
    host_acceptance: str = "unknown"
    host_trace_validation: str = "unknown"

    @property
    def passed(self) -> bool:
        return self.report is not None and self.report.status == "pass"


CaseStatus = Literal["succeeded", "failed", "cancelled", "skipped"]
QualityGate = Literal["passed", "failed"]


def _aggregate_execution(statuses) -> str:
    """Aggregate terminal operational states, independently of Judge verdicts."""
    states = set(statuses)
    for state in ('failed', 'blocked', 'cancelled', 'skipped'):
        if state in states:
            return state
    return 'completed' if states == {'completed'} else 'skipped'


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
    attempt_id: str | None = None
    attempt_number: int = 1

    @property
    def execution_status(self) -> str:
        """Separate a delivered verdict from infrastructure failure."""
        if self.status in {'cancelled', 'skipped'}:
            return self.status
        if ((self.artifacts or {}).get('completion') or {}).get('execution') == 'failed':
            return 'failed'
        if self.host_acceptance == 'rejected' or self.host_trace_validation == 'failed':
            return 'blocked'
        if self.benchmark is not None and self.benchmark.report is not None and self.error_type is None:
            return "completed"
        return {"failed": "blocked", "succeeded": "completed"}.get(self.status, self.status)

    @property
    def evidence_status(self) -> str:
        if self.benchmark is not None:
            return self.benchmark.evidence_status
        artifacts = self.artifacts or {}
        return artifacts.get('evidence_status') or (artifacts.get('completion') or {}).get('evidence') or 'unknown'

    @property
    def host_trace_validation(self) -> str:
        if self.benchmark is not None:
            return self.benchmark.host_trace_validation
        return (self.artifacts or {}).get('host_trace_validation') or 'unknown'

    @property
    def host_acceptance(self) -> str:
        """Explicit host evidence; a report alone cannot establish acceptance."""
        if self.benchmark is not None:
            return self.benchmark.host_acceptance
        artifacts = self.artifacts or {}
        if artifacts.get('host_acceptance'):
            return artifacts['host_acceptance']
        retained = artifacts.get('received_report')
        retained = retained if isinstance(retained, Mapping) else {}
        if retained.get('host_accepted') is True:
            return 'accepted'
        if retained.get('host_accepted') is False or self.host_trace_validation == 'failed':
            return 'rejected'
        return 'unknown'

    @property
    def judge_delivery_status(self) -> str:
        if self.judge_status is not None:
            return 'received'
        return (self.artifacts or {}).get('judge_delivery_status') or (
            'missing' if self.benchmark is not None else 'unknown')

    @property
    def quality_gate(self) -> QualityGate:
        """Keep the non-pass gate while excluding rejected or unfinished work."""
        return 'passed' if (self.execution_status == 'completed' and self.error_type is None
                            and self.benchmark is not None and self.benchmark.passed
                            and self.host_acceptance != 'rejected'
                            and self.host_trace_validation != 'failed'
                            and self.evidence_status not in {'missing', 'failed'}) else 'failed'

    @property
    def judge_status(self) -> str | None:
        """The verdict received for this Case, whether or not the host accepted it.

        A verdict received and billed before host validation rejected the run is
        retained in ``artifacts['received_report']``; counting only accepted
        reports summarised such a Case as "no report" beside the line naming it.
        Pass/fail and exit codes still come from accepted reports only.
        """
        report = self.benchmark.report if self.benchmark is not None else None
        if report is not None:
            return getattr(report, "status", None)
        retained = (self.artifacts or {}).get("received_report")
        status = retained.get("status") if isinstance(retained, Mapping) else None
        return status if isinstance(status, str) else None

    @property
    def judge_accepted(self) -> bool:
        """Legacy accepted-benchmark flag; explicit host evidence is host_acceptance."""
        return (self.benchmark is not None and self.benchmark.report is not None
                and self.error_type is None and self.host_acceptance != 'rejected'
                and self.host_trace_validation != 'failed')

    def __post_init__(self) -> None:
        if type(self.case_index) is not int or self.case_index < 0:
            raise ValueError("Case index must be a nonnegative integer")
        if type(self.attempt_number) is not int or self.attempt_number < 1:
            raise ValueError("Attempt number must be a positive integer")
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
        """Legacy aggregate; new consumers should use quality_gate."""
        return (self.preparation_error is None and len(self.case_results) == self.requested_case_count
                and all(case.status == "succeeded" for case in self.case_results))

    @property
    def execution_counts(self) -> dict[str, int]:
        counts = Counter(case.execution_status for case in self.case_results)
        missing = self.requested_case_count - len(self.case_results)
        if missing:
            counts['skipped'] += missing
        return dict(counts)

    @property
    def execution_status(self) -> str:
        if self.preparation_error is not None:
            return 'cancelled' if self.preparation_error.error_type == 'RunCancelled' else 'failed'
        return _aggregate_execution(self.execution_counts)

    @property
    def judge_counts(self) -> dict[str, int]:
        return dict(Counter(case.judge_status for case in self.case_results if case.judge_status is not None))

    @property
    def quality_gate(self) -> QualityGate:
        return 'passed' if (self.preparation_error is None
                            and len(self.case_results) == self.requested_case_count
                            and all(case.quality_gate == 'passed' for case in self.case_results)) else 'failed'

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

    @property
    def execution_counts(self) -> dict[str, int]:
        counts = Counter(item.execution_status for item in self.items)
        if self.skipped_count:
            counts['skipped'] += self.skipped_count
        return dict(counts)

    @property
    def execution_status(self) -> str:
        return _aggregate_execution(self.execution_counts)

    @property
    def case_execution_counts(self) -> dict[str, int]:
        counts = Counter()
        for item in self.items:
            counts.update(item.execution_counts)
        return dict(counts)

    @property
    def judge_counts(self) -> dict[str, int]:
        counts = Counter()
        for item in self.items:
            counts.update(item.judge_counts)
        return dict(counts)

    @property
    def quality_gate(self) -> QualityGate:
        return 'passed' if (self.skipped_count == 0
                            and all(item.quality_gate == 'passed' for item in self.items)) else 'failed'

    @property
    def exit_code(self) -> int:
        return 0 if self.quality_gate == 'passed' else 1

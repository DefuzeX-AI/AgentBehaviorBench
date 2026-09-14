"""Structured progress events emitted by benchmark orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


ProgressStage = Literal[
    "sdk_check",
    "agent_start",
    "case_generation",
    "benchmark_execution",
]
ProgressStatus = Literal["started", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class BenchmarkProgress:
    """One observable lifecycle transition in a benchmark run."""

    stage: ProgressStage
    status: ProgressStatus
    agent_id: str | None = None
    detail: str | None = None
    artifact_directory: str | None = None
    suite_id: str | None = None
    job_id: str | None = None
    agent_job_id: str | None = None
    registration_index: int | None = None
    phase: str | None = None
    case_index: int | None = None
    case_id: str | None = None
    artifact_run_id: str | None = None
    sdk_run_id: str | None = None
    event_timing: str | None = None
    case_count: int | None = None
    attempt_id: str | None = None
    attempt_number: int | None = None
    recovery_action: str | None = None


ProgressCallback = Callable[[BenchmarkProgress], None]


def emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: ProgressStage,
    status: ProgressStatus,
    agent_id: str | None = None,
    detail: str | None = None,
    artifact_directory: str | None = None,
    suite_id: str | None = None,
    job_id: str | None = None,
    agent_job_id: str | None = None,
    registration_index: int | None = None,
    phase: str | None = None,
    case_index: int | None = None,
    case_id: str | None = None,
    artifact_run_id: str | None = None,
    sdk_run_id: str | None = None,
    event_timing: str | None = None,
    case_count: int | None = None,
    attempt_id: str | None = None,
    attempt_number: int | None = None,
    recovery_action: str | None = None,
) -> None:
    """Emit an event only when the caller requested progress reporting."""

    if callback is not None:
        callback(
            BenchmarkProgress(
                stage=stage,
                status=status,
                agent_id=agent_id,
                detail=detail,
                artifact_directory=artifact_directory,
                suite_id=suite_id, job_id=job_id, agent_job_id=agent_job_id,
                registration_index=registration_index, phase=phase,
                case_index=case_index, case_id=case_id,
                artifact_run_id=artifact_run_id, sdk_run_id=sdk_run_id,
                event_timing=event_timing, case_count=case_count,
                attempt_id=attempt_id, attempt_number=attempt_number, recovery_action=recovery_action,
            )
        )

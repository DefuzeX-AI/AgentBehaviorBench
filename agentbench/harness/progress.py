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


ProgressCallback = Callable[[BenchmarkProgress], None]


def emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: ProgressStage,
    status: ProgressStatus,
    agent_id: str | None = None,
    detail: str | None = None,
    artifact_directory: str | None = None,
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
            )
        )

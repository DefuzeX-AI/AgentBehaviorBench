"""JSON export helpers for benchmark suite results."""

from __future__ import annotations

import json
import os
import tempfile
from threading import Lock
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path

from agentbench.harness.result import (
    BenchmarkResult,
    BenchmarkStepFailure,
    BenchmarkStepResult,
    BenchmarkSuiteResult,
    SuiteAgentResult,
)

_RESULT_WRITE_LOCK = Lock()


@dataclass(frozen=True)
class ResultLogWriter:
    """JSON event snapshot replaced atomically after each update."""

    path: Path
    suite_id: str

    def _append(self, event: Mapping[str, object]) -> None:
        append_result_event(self.path, {"suite_id": self.suite_id, **event})

    def append_step_started(
        self, agent_id: str, input_id: str, payload: object
    ) -> None:
        self._append(
            {
                "event": "step_started",
                "agent_id": agent_id,
                "input_id": input_id,
                "payload": _json_value(payload),
            },
        )

    def append_step_completed(self, agent_id: str, step: BenchmarkStepResult) -> None:
        self._append(
            {
                "event": "step_completed",
                "agent_id": agent_id,
                "step": _step_to_json(step),
            },
        )

    def append_step_failed(self, agent_id: str, failure: BenchmarkStepFailure) -> None:
        self._append(
            {
                "event": "step_failed",
                "agent_id": agent_id,
                "failure": _step_failure_to_json(failure),
            },
        )

    def append_agent_complete(self, item: SuiteAgentResult) -> None:
        self._append(
            {
                "event": "agent_completed",
                "agent_id": item.agent_id,
                "item": _suite_agent_to_json(item),
            },
        )

    def append_suite_complete(self, result: BenchmarkSuiteResult) -> None:
        if result.suite_id != self.suite_id:
            raise ValueError("Suite result ID does not match its result log")
        self._append(
            {
                "event": "suite_completed",
                "summary": _summary_to_json(result),
            },
        )

    def append_suite_error(self, exc: Exception) -> None:
        self._append(
            {
                "event": "suite_failed",
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
        )


def start_result_log(
    output_path: str | Path,
    *,
    suite_id: str,
    selected_agent_ids: tuple[str, ...],
    now: datetime | None = None,
) -> ResultLogWriter:
    """Create a unique JSON result snapshot with the run-start event."""

    if not suite_id.strip():
        raise ValueError("Suite ID cannot be empty")
    path = unique_result_log_path(output_path, now=now)
    append_result_event(
        path,
        {
            "event": "run_started",
            "suite_id": suite_id,
            "selected_agent_ids": list(selected_agent_ids),
        },
    )
    return ResultLogWriter(path=path, suite_id=suite_id)


def unique_result_log_path(
    output_path: str | Path, *, now: datetime | None = None
) -> Path:
    """Return a timestamped JSON path derived from the requested output path."""

    base = Path(output_path)
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    if base.suffix:
        directory = base.parent
        stem = base.stem
    elif base.exists() and base.is_dir():
        directory = base
        stem = "result"
    else:
        directory = base.parent
        stem = base.name or "result"

    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}-{timestamp}.json"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{timestamp}-{index}.json"
        index += 1
    return candidate


def append_result_event(path: str | Path, event: Mapping[str, object]) -> None:
    """Add an event and atomically replace the complete JSON document."""

    result_path = Path(path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with _RESULT_WRITE_LOCK:
        events = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
        if not isinstance(events, list) or not all(isinstance(item, dict) for item in events):
            raise ValueError("Result snapshot must contain an array of event objects")
        events.append(_json_value(event))
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=result_path.parent,
                prefix=f".{result_path.name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(events, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, result_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _summary_to_json(result: BenchmarkSuiteResult) -> dict[str, object]:
    return {
        "selected": result.selected_count,
        "attempted": result.attempted_count,
        "passed": result.passed_count,
        "failed": result.failed_count,
        "skipped": result.skipped_count,
        "suite_passed": result.passed,
    }


def _suite_agent_to_json(item: SuiteAgentResult) -> dict[str, object]:
    return {
        "agent_id": item.agent_id,
        "benchmark": (
            None if item.benchmark is None else _benchmark_to_json(item.benchmark)
        ),
        "benchmarks": [
            _benchmark_to_json(benchmark) for benchmark in item.benchmarks
        ],
        "requested_case_count": item.requested_case_count,
        "completed_case_count": item.completed_case_count,
        "error": (
            None
            if item.error_type is None
            else {"type": item.error_type, "message": item.error_message}
        ),
    }


def _benchmark_to_json(benchmark: BenchmarkResult) -> dict[str, object]:
    return {
        "agent_id": benchmark.agent_id,
        "adapter_name": benchmark.adapter_name,
        "run_id": benchmark.run_id,
        "run_state": benchmark.run_state,
        "provider_mode": benchmark.provider_mode,
        "passed": benchmark.passed,
        "history_count": benchmark.history_count,
        "report": _json_value(benchmark.report),
        "steps": [_step_to_json(step) for step in benchmark.steps],
    }


def _step_to_json(step: BenchmarkStepResult) -> dict[str, object]:
    return {
        "input_id": step.input_id,
        "payload": _json_value(step.payload),
        "output": _json_value(step.invocation.output),
        "raw_output": _json_value(step.invocation.raw_output),
    }


def _step_failure_to_json(failure: BenchmarkStepFailure) -> dict[str, object]:
    return {
        "input_id": failure.input_id,
        "payload": _json_value(failure.payload),
        "output": _json_value(failure.output),
        "raw_output": _json_value(failure.raw_output),
        "error": {
            "type": failure.error_type,
            "message": failure.error_message,
        },
    }


def _json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set | frozenset):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_value(model_dump())

    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return _json_value(dict_method())

    return repr(value)

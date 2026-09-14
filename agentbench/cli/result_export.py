"""JSON export helpers for benchmark suite results."""

from __future__ import annotations

import json
import os
import tempfile
import time
from threading import Lock
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from agentbench.harness.result import (
    BenchmarkResult,
    BenchmarkStepFailure,
    BenchmarkStepResult,
    BenchmarkSuiteResult,
    CaseResult,
    SuiteAgentResult,
)

_RESULT_WRITE_LOCK = Lock()
PROGRESS_FLUSH_SECONDS = 0.2
PROGRESS_BATCH_MAX_EVENTS = 256


def _environment_secrets(environ=None) -> tuple[str, ...]:
    values = os.environ if environ is None else environ
    return tuple(value for key, value in values.items()
                 if value and any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")))


@dataclass
class _ProgressBuffer:
    events: list = field(default_factory=list)
    started_at: float | None = None
    completed_agents: set[str] = field(default_factory=set)
    completed_cases: set[tuple[str, int]] = field(default_factory=set)


@dataclass(frozen=True)
class ResultLogWriter:
    """Coordinator-owned event log with atomic JSON array snapshots.

    Concurrent suites may batch ordinary progress until their next 200 ms
    coordinator tick. Lifecycle/terminal events always flush immediately.
    """

    path: Path
    suite_id: str
    batch_progress: bool = False
    secrets: tuple[str, ...] = field(default_factory=_environment_secrets, repr=False)
    _buffer: _ProgressBuffer = field(default_factory=_ProgressBuffer, init=False, repr=False, compare=False)

    def _append(self, event: Mapping[str, object]) -> None:
        event = _json_value({"suite_id": self.suite_id, "source": "abb",
                             "timestamp": datetime.now(timezone.utc).isoformat(), **event})
        self._buffer.events.append(event)
        ordinary_progress = (event.get("event") == "progress"
                             and event.get("status") not in {"succeeded", "failed", "cancelled"})
        if not self.batch_progress or not ordinary_progress or len(self._buffer.events) >= PROGRESS_BATCH_MAX_EVENTS:
            self.flush()
        else:
            if self._buffer.started_at is None:
                self._buffer.started_at = time.monotonic()
            self.flush_if_due()

    def flush_if_due(self) -> None:
        """Called by the coordinator, including while no new events arrive."""
        started = self._buffer.started_at
        if started is not None and time.monotonic() - started >= PROGRESS_FLUSH_SECONDS:
            self.flush()

    def flush(self) -> None:
        """Persist all pending events before returning or reporting an error."""
        if self._buffer.events:
            append_result_events(self.path, self._buffer.events, secrets=self.secrets)
            self._buffer.completed_agents.update(event["agent_id"] for event in self._buffer.events
                                                 if event.get("event") == "agent_completed"
                                                 and isinstance(event.get("agent_id"), str))
            self._buffer.completed_cases.update((event["agent_id"], event["case_index"]) for event in self._buffer.events
                                                if event.get("event") == "case_completed"
                                                and isinstance(event.get("agent_id"), str)
                                                and type(event.get("case_index")) is int)
            self._buffer.events.clear()
        self._buffer.started_at = None

    def append_event(self, event: Mapping[str, object]) -> None:
        """Persist a coordinator event, retaining its job and Case identity.

        Typed Case/Agent results are normalized before the event enters the
        ordered write buffer.
        """
        event = dict(event)
        if event.get("suite_id", self.suite_id) != self.suite_id:
            raise ValueError("Event suite ID does not match its result log")
        for key, kind, convert in (
            ("step", BenchmarkStepResult, _step_to_json),
            ("failure", BenchmarkStepFailure, _step_failure_to_json),
            ("item", SuiteAgentResult, _suite_agent_to_json),
            ("case_result", CaseResult, _case_to_json),
        ):
            if isinstance(event.get(key), kind):
                event[key] = convert(event[key])
        self._append(_json_value(event))

    def append_agent_complete(self, item: SuiteAgentResult) -> None:
        self._append(
            {
                "event": "agent_completed",
                "agent_id": item.agent_id,
                "item": _suite_agent_to_json(item),
            },
        )

    def append_partial_results(self, items) -> None:
        """Recover outcomes attached to an interruption without duplicate rows."""
        known = self._buffer.completed_agents | {
            event.get("agent_id") for event in self._buffer.events if event.get("event") == "agent_completed"
        }
        known_cases = self._buffer.completed_cases | {
            (event.get("agent_id"), event.get("case_index")) for event in self._buffer.events
            if event.get("event") == "case_completed"
        }
        for item in items:
            for case in item.case_results:
                key = (item.agent_id, case.case_index)
                if key not in known_cases:
                    self.append_event({"event": "case_completed", "agent_id": item.agent_id,
                                       "case_index": case.case_index, "case_id": case.case_id,
                                       "job_id": case.job_id, "status": case.status,
                                       "phase": "execute", "case_result": case})
                    known_cases.add(key)
            if item.agent_id not in known:
                self.append_agent_complete(item)
                known.add(item.agent_id)

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
    configured_workers: int = 1,
    effective_workers: int | None = None,
    total_case_count: int | None = None,
    selected_case_counts: Mapping[str, int] | None = None,
    batch_progress: bool = False,
    environ: Mapping[str, str] | None = None,
) -> ResultLogWriter:
    """Create a unique JSON result snapshot with the run-start event."""

    if not suite_id.strip():
        raise ValueError("Suite ID cannot be empty")
    path = unique_result_log_path(output_path, now=now)
    case_counts = dict(selected_case_counts or {agent: 1 for agent in selected_agent_ids})
    total_case_count = sum(case_counts.values()) if total_case_count is None else total_case_count
    writer = ResultLogWriter(path=path, suite_id=suite_id, batch_progress=batch_progress,
                             secrets=_environment_secrets(environ))
    writer._append(
        {
            "event": "run_started",
            "source": "abb",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suite_id": suite_id,
            "selected_agent_ids": list(selected_agent_ids),
            "configured_workers": configured_workers,
            "total_case_count": total_case_count,
            "selected_case_counts": case_counts,
            "effective_workers": (min(configured_workers, total_case_count)
                                  if effective_workers is None else effective_workers),
        },
    )
    return writer


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
    append_result_events(path, [event])


def append_result_events(path: str | Path, pending, *, secrets=None) -> None:
    """Append an ordered batch in one atomic replacement, preserving all rows."""

    result_path = Path(path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with _RESULT_WRITE_LOCK:
        events = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
        if not isinstance(events, list) or not all(isinstance(item, dict) for item in events):
            raise ValueError("Result snapshot must contain an array of event objects")
        from agentbench.observe.store import redact
        secrets = _environment_secrets() if secrets is None else secrets
        events.extend(redact(_json_value(event), secrets) for event in pending)
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
        "status": item.status,
        "case_results": [_case_to_json(case) for case in item.case_results],
        "benchmarks": [
            _benchmark_to_json(benchmark) for benchmark in item.benchmarks
        ],
        "requested_case_count": item.requested_case_count,
        "completed_case_count": item.completed_case_count,
        "attempted_case_count": item.attempted_case_count,
        "skipped_case_count": item.skipped_case_count,
        "preparation_error": _json_value(item.preparation_error),
        "error": (
            None
            if item.error_type is None
            else {"type": item.error_type, "message": item.error_message}
        ),
    }


def _case_to_json(case: CaseResult) -> dict[str, object]:
    return {"agent_id": case.agent_id, "case_index": case.case_index,
            "job_id": case.job_id, "case_id": case.case_id, "status": case.status,
            "artifacts": _json_value(case.artifacts),
            "benchmark": None if case.benchmark is None else _benchmark_to_json(case.benchmark),
            "error": None if case.error_type is None else {"type": case.error_type, "message": case.error_message}}


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

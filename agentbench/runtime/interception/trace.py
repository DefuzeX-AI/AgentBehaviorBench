"""Structured model interception trace events and sinks."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from agentbench.runtime.contracts.execution import RunControl, RuntimeInfrastructureError


TRACE_PREFIX = "DEFUZEX_TRACE "
DEFAULT_TRACE_MAX_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event: str
    data: Mapping[str, object]

    @classmethod
    def from_log_line(cls, line: str) -> "TraceEvent | None":
        if not line.startswith(TRACE_PREFIX):
            return None
        try:
            payload = json.loads(line[len(TRACE_PREFIX) :])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        event = payload.pop("event", None)
        if not isinstance(event, str) or not event:
            return None
        return cls(event=event, data=payload)


@runtime_checkable
class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None:
        ...


class NullTraceSink:
    def emit(self, event: TraceEvent) -> None:
        del event


class InterceptionTraceState:
    """Track completed request/response pairs for required interception."""

    def __init__(self) -> None:
        self._requests: set[str] = set()
        self._responses: set[str] = set()
        self._completed: list[str] = []
        self._condition = threading.Condition()
        self._last_event = time.monotonic()
        self._failed = False
        self._persistence_error: Exception | None = None

    def fail(self, error: Exception | None = None) -> None:
        """A failed trace write must never count as a completed observation."""
        with self._condition:
            self._failed = True
            if error is not None and self._persistence_error is None:
                self._persistence_error = error
            self._condition.notify_all()

    def check_persistence(self) -> None:
        """Evidence loss is a Suite failure, even for generation-only sessions."""
        with self._condition:
            if self._persistence_error is not None:
                raise RuntimeInfrastructureError(
                    f"Model trace persistence failed: {self._persistence_error}"
                ) from self._persistence_error

    def emit(self, event: TraceEvent) -> None:
        call_id = event.data.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            return
        with self._condition:
            if event.event == "llm_error" or event.data.get("truncated"):
                self._failed = True
                self._condition.notify_all()
            self._last_event = time.monotonic()
            if event.event == "llm_request":
                self._requests.add(call_id)
            elif event.event == "llm_response":
                self._responses.add(call_id)
            if (
                call_id in self._requests
                and call_id in self._responses
                and call_id not in self._completed
            ):
                self._completed.append(call_id)
                self._condition.notify_all()

    def checkpoint(self) -> int:
        with self._condition:
            return len(self._completed)

    def wait_for_completion_after(self, checkpoint: int, timeout: float,
                                  control: RunControl | None = None) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self._completed) <= checkpoint:
                self.check_persistence()
                if control is not None:
                    control.check()
                if self._failed:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(min(0.1, remaining))
            if control is not None:
                control.check()
            self.check_persistence()
            return not self._failed

    def wait_for_idle(self, *, timeout: float = 2, quiet: float = 0.3,
                      control: RunControl | None = None) -> bool:
        """Drain final log events and reject requests with no corresponding response."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                self.check_persistence()
                if control is not None:
                    control.check()
                if self._failed:
                    return False
                idle_for = time.monotonic() - self._last_event
                if idle_for >= quiet and self._requests <= self._responses:
                    return True
                self._condition.wait(timeout=min(0.05, max(0, deadline - time.monotonic())))
        return False

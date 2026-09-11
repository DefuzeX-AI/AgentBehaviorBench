"""Structured model interception trace events and sinks."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, runtime_checkable


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

    def fail(self) -> None:
        """A failed trace write must never count as a completed observation."""
        with self._condition:
            self._failed = True
            self._condition.notify_all()

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

    def wait_for_completion_after(self, checkpoint: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self._completed) <= checkpoint:
                if self._failed:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return not self._failed

    def wait_for_idle(self, *, timeout: float = 2, quiet: float = 0.3) -> bool:
        """Drain final log events and reject requests with no corresponding response."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                if self._failed:
                    return False
                idle_for = time.monotonic() - self._last_event
                if idle_for >= quiet and self._requests <= self._responses:
                    return True
                self._condition.wait(timeout=min(0.05, max(0, deadline - time.monotonic())))
        return False


@dataclass(slots=True)
class TerminalTraceSink:
    output_fn: Callable[[str], None] = print

    def emit(self, event: TraceEvent) -> None:
        if event.event == "interceptor_ready":
            return
        data = event.data
        call_id = data.get("call_id", "-")
        route = data.get("route_id", "-")
        direction = "REQUEST" if event.event == "llm_request" else "RESPONSE"
        source = ""
        if data.get("source_host"):
            source = (
                f" source={data.get('source_host', '')}"
                f"{data.get('source_path', '')}"
            )
        self.output_fn(
            f"[LLM TRACE {direction}] call={call_id} route={route} "
            f"provider={data.get('provider', '-')} "
            f"{data.get('method', '')} {data.get('host', '')}{data.get('path', '')}"
            f"{source}".rstrip()
        )
        metadata = {
            key: data[key]
            for key in (
                "source_model",
                "model",
                "status",
                "latency_ms",
                "streaming",
                "routing_error",
                "truncated",
            )
            if key in data
        }
        if metadata:
            self.output_fn(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
        if "payload" in data:
            self.output_fn(
                json.dumps(data["payload"], ensure_ascii=False, indent=2, sort_keys=True)
            )

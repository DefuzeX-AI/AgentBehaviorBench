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
    def from_log_line(cls, line: str, prefix: str = TRACE_PREFIX) -> "TraceEvent | None":
        if not line.startswith(prefix):
            return None
        try:
            payload = json.loads(line[len(prefix) :])
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
    """Track recorded request terminal states, independently of Agent success.

    An observed upstream/transport failure ends a call without inventing a
    response. Authentication, conversion and capture failures still reject
    evidence. A transport error alone does not identify who cancelled. A refused
    non-model destination is the Agent's behavior, not lost evidence (#137): it
    is counted and reported, and acceptance still requires completed model calls.
    """

    def __init__(self) -> None:
        self._requests: set[str] = set()
        self._responses: set[str] = set()
        self._terminated: set[str] = set()
        self._errors: dict[str, str] = {}
        self._completed: list[str] = []
        self._condition = threading.Condition()
        self._last_event = time.monotonic()
        self._failed = False
        self._persistence_error: Exception | None = None
        # The first event that rejected the evidence, and request order for the
        # first unfinished call: an operator needs a call to look up, not counts.
        self._first_rejection: str | None = None
        self._request_order: list[str] = []
        self._auxiliary_pending: set[str] = set()
        self._required_pending: set[str] = set()
        self._operation_failure: str | None = None
        self._denied: set[str] = set()

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
            if event.event == 'observation_error':
                self._failed = True
                self._note_rejection(event, call_id, 'capture_failed')
            if event.event == 'tool_request' and event.data.get('required') is True:
                self._required_pending.add(call_id)
            elif event.event in ('tool_response', 'tool_error') and call_id in self._required_pending:
                self._required_pending.discard(call_id)
                status = event.data.get('status')
                if event.event == 'tool_error' or not isinstance(status, int) or status >= 400:
                    self._operation_failure = f'{call_id[:64]} required network operation failed'
            if event.event == 'model_auxiliary_request':
                self._auxiliary_pending.add(call_id)
            elif event.event in ('model_auxiliary_response', 'model_auxiliary_error'):
                self._auxiliary_pending.discard(call_id)
            if event.event == "llm_error":
                code = event.data.get('error_code')
                self._errors[call_id] = code if isinstance(code, str) else 'unclassified'
                if code in {'transport_error', 'upstream_error'}:
                    self._terminated.add(call_id)
                elif code == 'egress_denied' and event.data.get('request_kind') != 'model':
                    self._denied.add(call_id)
                else:
                    self._failed = True
                    self._note_rejection(event, call_id, self._errors[call_id])
            if event.data.get("truncated"):
                self._failed = True
                self._note_rejection(event, call_id, 'truncated')
            self._last_event = time.monotonic()
            if event.event == "llm_request":
                if call_id not in self._requests:
                    self._request_order.append(call_id)
                self._requests.add(call_id)
            elif event.event == "llm_response":
                self._responses.add(call_id)
            if (
                call_id in self._requests
                and call_id in self._responses | self._terminated
                and call_id not in self._completed
            ):
                self._completed.append(call_id)
            self._condition.notify_all()

    def _note_rejection(self, event: TraceEvent, call_id: str, reason: str) -> None:
        if self._first_rejection is not None:
            return
        host, path = event.data.get('source_host'), event.data.get('source_path')
        location = ' '.join(str(part)[:200] for part in (host, path) if isinstance(part, str) and part)
        self._first_rejection = (f'{call_id[:64]} {event.event} {reason[:64]}'
                                 + (f' {location}' if location else ''))

    def diagnostic(self) -> str:
        """Return bounded classifications/counts, never exception text or argv.

        The first rejecting event and the first unfinished call are named by call
        ID, event, error code and source host/path -- the fields to look up in the
        network trace -- so a rejection can be traced without reading every event.
        """
        with self._condition:
            unfinished = self._requests - self._responses - self._terminated
            known = {'egress_denied', 'authentication_failed', 'request_preparation_failed',
                     'upstream_error', 'response_conversion_failed', 'stream_processing_failed',
                     'transport_error'}
            codes = sorted({code if code in known else 'unclassified' for code in self._errors.values()})
            text = (f'requests={len(self._requests)}, responses={len(self._responses)}, '
                    f'observed_failures={len(self._terminated)}, unfinished={len(unfinished)}, '
                    f'errors={",".join(codes) or "none"}, capture_rejected={self._failed}')
            if self._denied:
                text += f', egress_denied={len(self._denied)}'
            if self._first_rejection is not None:
                text += f', first_rejection={self._first_rejection}'
            first_unfinished = next((call for call in self._request_order if call in unfinished), None)
            if first_unfinished is not None:
                text += f', first_unfinished={first_unfinished[:64]}'
            if self._auxiliary_pending:
                text += f', auxiliary_pending={len(self._auxiliary_pending)}'
            if self._required_pending:
                text += f', required_pending={len(self._required_pending)}'
            if self._operation_failure:
                text += f', operation_failure={self._operation_failure}'
            if self._persistence_error is not None and self._first_rejection is None:
                text += ', first_rejection=trace persistence failure'
            return text

    def checkpoint(self) -> int:
        with self._condition:
            return len(self._completed)

    @property
    def operation_failure(self) -> str | None:
        """A required native operation failed, independently of capture validity."""
        with self._condition:
            return self._operation_failure

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
        """Drain events and reject requests with no observed terminal outcome."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                self.check_persistence()
                if control is not None:
                    control.check()
                if self._failed or self._operation_failure:
                    return False
                idle_for = time.monotonic() - self._last_event
                if (idle_for >= quiet and not self._auxiliary_pending and not self._required_pending
                        and self._requests <= self._responses | self._terminated):
                    return True
                self._condition.wait(timeout=min(0.05, max(0, deadline - time.monotonic())))
        return False

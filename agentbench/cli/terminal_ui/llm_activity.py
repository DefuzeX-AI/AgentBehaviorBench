"""Temporary terminal panel showing intercepted LLM activity."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from builtins import print as builtin_print
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agentbench.runtime.interception import TraceEvent

from .constants import (
    ANSI_RESET,
    ANSI_YELLOW,
)
from .evaluation_http import EvaluationHTTPFormatter
from .formatting import case_identity, short_id
from .live_cases import LiveCases

PREVIEW_CHAR_LIMIT = 72
ACTIVITY_ANIMATION_INTERVAL_SECONDS = 0.35
DOT_FRAMES = (".  ", ".. ", "...")


@dataclass(slots=True)
class _CallActivity:
    call_id: str
    call_number: int
    provider: str
    request_preview: str
    started_at: float
    response_preview: str | None = None
    status: object | None = None
    latency_ms: object | None = None
    error: str | None = None

    @property
    def active(self) -> bool:
        return self.response_preview is None and self.error is None


class LLMActivity:
    """
        Render one short, self-erasing panel for the current LLM call.
    
    """

    def __init__(
        self,
        output_fn: Callable[[str], None] = print,
        *,
        live_updates: bool | None = None,
        preview_chars: int = PREVIEW_CHAR_LIMIT,
        animation_interval: float = ACTIVITY_ANIMATION_INTERVAL_SECONDS,
    ) -> None:
        if preview_chars < 1:
            raise ValueError("preview_chars must be positive")
        self._output_fn = output_fn
        terminal_columns = shutil.get_terminal_size((100, 24)).columns
        self._preview_chars = min(preview_chars, max(8, terminal_columns - 16))
        self._animation_interval = animation_interval
        self._live_updates = (
            output_fn is builtin_print and sys.stdout.isatty()
            if live_updates is None
            else live_updates
        )
        self._lock = threading.RLock()
        self._stop_animation = threading.Event()
        self._animation_thread: threading.Thread | None = None
        self._stage_label: str | None = None
        self._stage_frame = 0
        self._calls: OrderedDict[str, _CallActivity] = OrderedDict()
        self._evaluation_http = EvaluationHTTPFormatter()
        self._latest_call_id: str | None = None
        self._call_count = 0
        self._rendered_line_count = 0
        self._concurrent = False
        self._live_cases: LiveCases | None = None

    def set_concurrent(self, enabled: bool) -> None:
        """Use permanent identity-prefixed events when several Agents run."""
        self.close()
        self._concurrent = enabled

    def set_live_cases(self, display: LiveCases | None) -> None:
        """Send concurrent trace updates to one shared terminal dashboard."""
        self._live_cases = display

    def start_stage(self, label: str) -> None:
        """Start the benchmark stage line and its shared animation loop."""

        self._stop_animation_thread()
        with self._lock:
            self._clear_live_block_locked()
            self._stage_label = label.rstrip(".")
            self._stage_frame = 0
            self._calls.clear()
            self._evaluation_http.reset()
            self._latest_call_id = None
            self._call_count = 0
            if not self._live_updates:
                self._output_fn(label)
                return
            self._stop_animation.clear()
            self._render_live_block_locked()

        self._animation_thread = threading.Thread(
            target=self._animate,
            daemon=True,
            name="defuzex-llm-activity",
        )
        self._animation_thread.start()

    def finish_stage(self, status: str) -> None:
        """Erase the temporary panel and leave only the final stage result."""

        self._stop_animation_thread()
        with self._lock:
            label = self._stage_label or "Stage"
            if not self._live_updates:
                self._output_fn(f"  {status}")
            else:
                self._clear_live_block_locked()
                sys.stdout.write(f"  {label}... {status}\n")
                sys.stdout.flush()
            self._reset_locked()

    def emit(self, event: TraceEvent) -> None:
        """Consume one structured interception event."""

        if event.event == "interceptor_ready":
            return
        if self._live_cases is not None:
            self._live_cases.on_trace(event)
            return
        if self._concurrent:
            self._emit_concurrent(event)
            return
        if (event.event in {'tool_request', 'tool_response', 'tool_error'}
                and event.data.get('purpose') == 'evaluation'):
            self._write_evaluation_http(event)
            return
        if event.event not in {"llm_request", "llm_response", "llm_error"}:
            return
        call_id = event.data.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            return

        with self._lock:
            if event.event == "llm_request":
                preview = _event_preview(event, self._preview_chars)
                self._call_count += 1
                self._calls[call_id] = _CallActivity(
                    call_id=call_id,
                    call_number=self._call_count,
                    provider=_provider(event.data),
                    request_preview=preview,
                    started_at=time.monotonic(),
                )
                self._latest_call_id = call_id
                if not self._live_updates:
                    call = self._calls[call_id]
                    self._output_fn(self._call_header(call))
                    self._output_fn(f"      Agent > {preview}")
                    self._output_fn(f"      {self._model_text(call)}")
                    return
            else:
                call = self._calls.get(call_id)
                if call is None:
                    self._call_count += 1
                    call = _CallActivity(
                        call_id=call_id,
                        call_number=self._call_count,
                        provider=_provider(event.data),
                        request_preview="-",
                        started_at=time.monotonic(),
                    )
                    self._calls[call_id] = call
                self._latest_call_id = call_id
                if event.event == "llm_response":
                    call.response_preview = _event_preview(
                        event, self._preview_chars
                    )
                    call.status = event.data.get("status")
                    call.latency_ms = event.data.get("latency_ms")
                else:
                    call.error = _truncate_preview(
                        str(event.data.get("error", "LLM request failed")),
                        self._preview_chars,
                    )
                if not self._live_updates:
                    self._output_fn(self._call_header(call))
                    self._output_fn(f"      {self._model_text(call)}")
                    return

            if self._stage_label is not None:
                self._render_live_block_locked()

    def _emit_concurrent(self, event: TraceEvent) -> None:
        # No mutable call panel: identical call IDs in separate jobs cannot
        # overwrite each other's display state, even when traces arrive late.
        data = event.data
        if event.event.startswith("tool_"):
            if data.get("purpose") == "evaluation":
                self._write_evaluation_http(event)
            return
        if event.event not in {"llm_request", "llm_response", "llm_error"}:
            return
        identity = case_identity(data.get("agent_id"), data.get("case_index"), data.get("job_id"))
        call_id = data.get("call_id")
        hint = f" #{short_id(call_id, 6)}" if call_id else ""
        if event.event == "llm_error":
            label = f"Model error{hint}"
            preview = _truncate_preview(str(data.get("error", "Request failed")), self._preview_chars)
        else:
            label = (f"Model → {_provider(data)}{hint}" if event.event == "llm_request"
                     else f"Model ← HTTP {data.get('status', '?')}{hint}")
            preview = _event_preview(event, self._preview_chars)
        with self._lock:
            self._output_fn(f"{identity} {label} · {preview}")

    def _write_evaluation_http(self, event: TraceEvent) -> None:
        """Summarize routine SDK polling; always expose failures immediately."""
        with self._lock:
            line = self._evaluation_http.render(event)
            if line is not None:
                if self._concurrent:
                    self._output_fn(line)
                else:
                    self.write_static('    ' + line)

    def write_static(self, text: str) -> None:
        """Print permanent output without corrupting the temporary panel."""

        if not self._live_updates:
            self._output_fn(text)
            return
        with self._lock:
            self._clear_live_block_locked()
            sys.stdout.write(f"{text}\n")
            if self._stage_label is not None:
                self._render_live_block_locked()
            sys.stdout.flush()

    def clear_activity(self) -> None:
        """Remove call details while preserving an active stage line."""

        with self._lock:
            self._calls.clear()
            self._latest_call_id = None
            if self._live_updates and self._stage_label is not None:
                self._render_live_block_locked()

    def close(self) -> None:
        """Stop animation and erase all temporary terminal content."""

        self._stop_animation_thread()
        with self._lock:
            self._clear_live_block_locked()
            self._reset_locked()

    def _animate(self) -> None:
        while not self._stop_animation.wait(self._animation_interval):
            with self._lock:
                if self._stage_label is None:
                    return
                self._stage_frame += 1
                self._render_live_block_locked()

    def _stop_animation_thread(self) -> None:
        thread = self._animation_thread
        if thread is None:
            return
        self._stop_animation.set()
        if thread is not threading.current_thread():
            thread.join(timeout=self._animation_interval + 0.2)
        self._animation_thread = None
        self._stop_animation.clear()

    def _render_live_block_locked(self) -> None:
        if not self._live_updates or self._stage_label is None:
            return
        stage_dots = DOT_FRAMES[self._stage_frame % len(DOT_FRAMES)]
        lines = [
            f"  {self._stage_label}{stage_dots} "
            f"{ANSI_YELLOW}RUNNING{ANSI_RESET}"
        ]
        call = self._displayed_call()
        if call is not None:
            lines.extend(
                (
                    self._call_header(call),
                    f"      Agent > {call.request_preview}",
                    f"      {self._model_text(call)}",
                )
            )

        self._clear_live_block_locked()
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()
        self._rendered_line_count = len(lines)

    def _displayed_call(self) -> _CallActivity | None:
        for call in reversed(tuple(self._calls.values())):
            if call.active:
                return call
        if self._latest_call_id is None:
            return None
        return self._calls.get(self._latest_call_id)

    def _call_header(self, call: _CallActivity) -> str:
        elapsed = _format_duration(self._elapsed_seconds(call))
        if call.error is not None:
            state = "FAILED"
        elif call.response_preview is None:
            dots = DOT_FRAMES[self._stage_frame % len(DOT_FRAMES)]
            state = f"waiting {elapsed} {dots}"
        else:
            state = str(call.status) if call.status is not None else "done"
            state = f"{state} | {elapsed}"

        active_count = sum(item.active for item in self._calls.values())
        concurrent = f" | {active_count} active" if active_count > 1 else ""
        return (
            f"    LLM call {call.call_number:02d} | {call.provider} | "
            f"{state}{concurrent}"
        )

    def _model_text(self, call: _CallActivity) -> str:
        if call.error is not None:
            return f"Model < FAILED: {call.error}"
        if call.response_preview is None:
            return "Model < waiting..."
        return f"Model < {call.response_preview}"

    @staticmethod
    def _elapsed_seconds(call: _CallActivity) -> float:
        if isinstance(call.latency_ms, (int, float)):
            return float(call.latency_ms) / 1000
        return time.monotonic() - call.started_at

    def _clear_live_block_locked(self) -> None:
        count = self._rendered_line_count
        if count == 0:
            return
        sys.stdout.write("\r")
        if count > 1:
            sys.stdout.write(f"\033[{count - 1}A")
        for index in range(count):
            sys.stdout.write("\033[2K")
            if index < count - 1:
                sys.stdout.write("\n")
        sys.stdout.write("\r")
        if count > 1:
            sys.stdout.write(f"\033[{count - 1}A")
        self._rendered_line_count = 0

    def _reset_locked(self) -> None:
        self._stage_label = None
        self._calls.clear()
        self._evaluation_http.reset()
        self._latest_call_id = None
        self._call_count = 0
        self._stage_frame = 0


def _event_preview(event: TraceEvent, limit: int) -> str:
    payload = event.data.get("payload")
    if event.event == "llm_request":
        text = _request_text(payload)
    else:
        text = _response_text(payload)
    return _truncate_preview(text or "-", limit)


def _provider(data: Mapping[str, object]) -> str:
    provider = data.get("provider")
    return provider if isinstance(provider, str) and provider else "model"


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes:02d}:{remaining_seconds:02d}"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours:02d}:{remaining_minutes:02d}:{remaining_seconds:02d}"


def _request_text(payload: object) -> str:
    if isinstance(payload, Mapping):
        messages = payload.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                text = _content_text(message)
                if text:
                    return text
        for key in ("input", "prompt", "contents"):
            value = payload.get(key)
            text = _latest_content_text(value)
            if text:
                return text
        tool = _tool_text(payload)
        if tool:
            return tool
    return _fallback_text(payload)


def _response_text(payload: object) -> str:
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            text = _content_text(choices[0])
            if text:
                return text
        for key in ("output_text", "output", "content", "events", "response"):
            text = _content_text(payload.get(key))
            if text:
                return text
        tool = _tool_text(payload)
        if tool:
            return tool
    return _fallback_text(payload)


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return _normalize(value)
    if isinstance(value, list):
        parts = [_content_text(item) for item in value]
        return _normalize(" ".join(part for part in parts if part))
    if not isinstance(value, Mapping):
        return ""

    for key in ("content", "text", "output_text", "input_text", "delta"):
        text = _content_text(value.get(key))
        if text:
            return text
    for key in ("message", "choices", "output", "events", "response"):
        text = _content_text(value.get(key))
        if text:
            return text
    return _tool_text(value)


def _latest_content_text(value: object) -> str:
    if isinstance(value, list):
        for item in reversed(value):
            text = _content_text(item)
            if text:
                return text
        return ""
    return _content_text(value)


def _tool_text(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = _tool_text(item)
            if text:
                return text
        return ""
    if not isinstance(value, Mapping):
        return ""

    for key in ("tool_calls", "tools", "function", "tool_use"):
        if key in value:
            text = _tool_text(value[key])
            if text:
                return text
    name = value.get("name")
    if isinstance(name, str) and name:
        return f"Tool: {name}"
    return ""


def _fallback_text(payload: object) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return _normalize(payload)
    try:
        return _normalize(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
    except (TypeError, ValueError):
        return _normalize(str(payload))


def _truncate_preview(text: str, limit: int) -> str:
    normalized = _normalize(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def _normalize(text: str) -> str:
    return " ".join(text.split())


__all__ = ["LLMActivity", "PREVIEW_CHAR_LIMIT"]

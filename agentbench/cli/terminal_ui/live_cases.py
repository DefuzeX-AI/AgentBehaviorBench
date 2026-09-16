"""A bounded, redrawable view of the Cases actually running in parallel."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from dataclasses import dataclass
from typing import TextIO

from agentbench.harness.progress import BenchmarkProgress
from agentbench.runtime.interception import TraceEvent

from .generation_progress import GenerationProgress, read_generation_progress
from .presentation import format_case_event


@dataclass(slots=True)
class _CaseRow:
    stage: str = "STARTING"
    detail: str = "Waiting for agent"
    model_calls: int = 0


class LiveCases:
    """Keep one terminal row per active Case, up to the visible screen height."""

    def __init__(self, case_counts: dict[str, int], workers: int, *, stream: TextIO | None = None,
                 refresh_seconds: float = 0.15) -> None:
        self._stream = stream or sys.stdout
        self._counts = dict(case_counts)
        self._workers = workers
        self._rows: dict[tuple[str, int], _CaseRow] = {}
        self._completed: set[tuple[str, int]] = set()
        self._prepared: set[tuple[str, int]] = set()
        self._generation: dict[str, GenerationProgress] = {}
        self._lock = threading.RLock()
        self._refresh_seconds = refresh_seconds
        self._last_render = 0.0
        self._rendered_lines = 0
        self._dirty = False
        self._active = False
        self._closed = False

    def on_progress(self, event: BenchmarkProgress) -> None:
        """Show preparation and execution stages without printing every event."""
        agent = event.agent_id
        if not agent:
            return
        with self._lock:
            if event.stage == "case_generation" and event.phase == "generate":
                total = event.case_count or self._counts.get(agent, 0)
                if total > 0 and agent not in self._generation:
                    self._generation[agent] = GenerationProgress(total, None, 0, 0)
                self._active = True
            elif event.stage == "benchmark_execution" and type(event.case_index) is int:
                row = self._rows.get((agent, event.case_index))
                if row is not None:
                    if event.status == "started":
                        row.stage, row.detail = "STARTING", "Agent container ready"
                    elif event.status == "failed":
                        row.stage, row.detail = "ERROR", _fit(event.detail or "Execution failed", 48)
                    elif event.status == "succeeded":
                        row.stage, row.detail = "FINISHING", "Validating results"
            self._dirty = True
            self._render_locked(force=True)

    def on_event(self, event: dict) -> None:
        """Update active slots from the same Case events saved in result logs."""
        kind = event.get("event")
        agent, index = event.get("agent_id"), event.get("case_index")
        if not isinstance(agent, str) or type(index) is not int:
            return
        key = (agent, index)
        with self._lock:
            if kind == "case_prepared":
                self._prepared.add(key)
                progress = self._generation.get(agent)
                if progress is not None:
                    ready = sum(name == agent for name, _ in self._prepared)
                    self._generation[agent] = GenerationProgress(progress.total, None, ready, progress.failed)
            elif kind == "case_started":
                self._completed.discard(key)
                self._rows[key] = _CaseRow("STARTING", "Retrying" if event.get("status") == "retrying"
                                               else "Waiting for agent")
                self._active = True
            elif kind == "case_completed":
                self._rows.pop(key, None)
                self._completed.add(key)
                progress = self._generation.get(agent)
                if progress is not None and event.get("phase") == "generate":
                    failed = sum(name == agent for name, case in self._completed
                                 if (name, case) not in self._prepared)
                    self._generation[agent] = GenerationProgress(progress.total, None, progress.ready, failed)
                self._write_locked(format_case_event(event))
            else:
                return
            self._dirty = True
            self._render_locked(force=True)

    def on_trace(self, event: TraceEvent) -> None:
        """Show Case generation counts and the current stage of each worker."""
        data = event.data
        agent, index = data.get("agent_id"), data.get("case_index")
        with self._lock:
            if isinstance(agent, str) and data.get("phase") == "generate":
                progress = read_generation_progress(data)
                if progress is not None and progress != self._generation.get(agent):
                    self._generation[agent] = progress
                    self._active = True
                    self._dirty = True
            elif isinstance(agent, str) and type(index) is int:
                row = self._rows.get((agent, index))
                if row is None:
                    return
                previous = (row.stage, row.detail, row.model_calls)
                if event.event == "llm_request":
                    row.model_calls += 1
                    row.stage, row.detail = "AGENT", f"Model call {row.model_calls}"
                elif event.event == "llm_response":
                    row.stage, row.detail = "AGENT", f"Model replied · {row.model_calls} calls"
                elif event.event == "llm_error":
                    row.stage, row.detail = "ERROR", _fit(str(data.get("error") or "Model failed"), 48)
                    self._write_locked(f"[{agent} · case {index + 1}] Model error · {row.detail}")
                elif event.event == "tool_request" and data.get("purpose") == "evaluation":
                    path = str(data.get("path") or "")
                    if "/judge/" in path:
                        row.stage, row.detail = "JUDGE", "Submitting for judgment"
                    elif "/operations/" in path and row.stage == "JUDGE":
                        row.detail = "Waiting for verdict"
                elif event.event in {"tool_response", "tool_error"} and data.get("purpose") == "evaluation":
                    status = data.get("status")
                    if event.event == "tool_error" or (str(status).isdigit() and int(str(status)) >= 400):
                        row.stage = "ERROR"
                        row.detail = _fit(str(data.get("error") or f"SDK HTTP {status}"), 48)
                        self._write_locked(f"[{agent} · case {index + 1}] SDK error · {row.detail}")
                if (row.stage, row.detail, row.model_calls) != previous:
                    self._dirty = True
            self._render_locked()

    def write(self, line: str) -> None:
        """Print a permanent message above the live block without corrupting it."""
        with self._lock:
            self._write_locked(line)
            self._render_locked(force=True)

    def flush(self) -> None:
        """Render deferred changes on the Suite event loop's normal tick."""
        with self._lock:
            self._render_locked(force=True)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._clear_locked()
            self._stream.flush()
            self._closed = True

    def snapshot_lines(self) -> list[str]:
        """Return the current bounded view for tests and non-terminal inspection."""
        with self._lock:
            return self._snapshot_lines_locked()

    def _write_locked(self, line: str) -> None:
        self._clear_locked()
        self._stream.write(f"{line}\n")
        self._stream.flush()

    def _render_locked(self, *, force: bool = False) -> None:
        if not self._active or self._closed:
            return
        if not self._dirty and self._rendered_lines:
            return
        now = time.monotonic()
        if not force and now - self._last_render < self._refresh_seconds:
            return
        lines = self._snapshot_lines_locked()
        self._clear_locked()
        self._stream.write("\n".join(lines) + "\n")
        self._stream.flush()
        self._rendered_lines = len(lines)
        self._last_render = now
        self._dirty = False

    def _clear_locked(self) -> None:
        if self._rendered_lines:
            self._stream.write(f"\x1b[{self._rendered_lines}F\x1b[J")
            self._rendered_lines = 0

    def _snapshot_lines_locked(self) -> list[str]:
        size = shutil.get_terminal_size((100, 24))
        width = max(20, min(size.columns - 1, 100))
        total = sum(self._counts.values())
        running = len(self._rows)
        completed = len(self._completed)
        pending = max(0, total - running - completed)
        title = f"LIVE CASES  {running} running / {total} total · {self._workers} workers"
        lines = [_rule(title, width)]
        for agent, progress in sorted(self._generation.items()):
            if progress.active_index is not None:
                detail = (f"{agent}: generating Case {progress.active_index + 1}/{progress.total}"
                          f" · {progress.ready} saved")
            elif progress.ready == progress.total:
                detail = f"{agent}: generation complete · {progress.ready}/{progress.total} saved"
            else:
                detail = f"{agent}: preparing Cases · {progress.ready}/{progress.total} saved"
            if progress.failed:
                detail += f" · {progress.failed} failed"
            lines.append(_box(detail, width))
        lines.append(_box("AGENT / CASE                 STAGE       ACTIVITY", width))
        visible = max(1, size.lines - len(lines) - 3)
        for (agent, index), row in sorted(self._rows.items())[:visible]:
            detail = f"{_fit(agent, 20):<20} #{index + 1:02d}    {row.stage:<10}  {row.detail}"
            lines.append(_box(detail, width))
        hidden = max(0, running - visible)
        if hidden:
            lines.append(_box(f"… {hidden} more running Cases outside the visible terminal height", width))
        lines.append(_box(f"{pending} pending · {completed} finished", width))
        lines.append("+" + "-" * (width - 2) + "+")
        return lines


def _fit(value: str, width: int) -> str:
    return value if len(value) <= width else value[:width - 1] + "…"


def _box(value: str, width: int) -> str:
    inner = width - 4
    return "| " + _fit(value, inner).ljust(inner) + " |"


def _rule(title: str, width: int) -> str:
    content = " " + _fit(title, width - 4) + " "
    return "+" + content + "-" * (width - 2 - len(content)) + "+"

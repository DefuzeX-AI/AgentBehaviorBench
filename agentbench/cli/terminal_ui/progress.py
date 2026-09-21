"""Colored terminal rendering for benchmark progress events."""

from __future__ import annotations

import sys
from builtins import print as builtin_print
from collections.abc import Callable
from threading import Event, Lock, Thread

from agentbench.harness.progress import BenchmarkProgress

from . import LLMActivity
from .constants import ANSI_GREEN, ANSI_RED, ANSI_RESET, ANSI_YELLOW
from .formatting import case_identity
from .live_cases import LiveCases

DOT_FRAMES = (".  ", ".. ", "...")
ANIMATION_INTERVAL_SECONDS = 0.35


class ProgressPrinter:
    """Render structured Harness events without coupling it to terminal I/O."""

    def __init__(
        self,
        output_fn: Callable[[str], None] = print,
        *,
        llm_activity: LLMActivity | None = None,
        live_updates: bool | None = None,
        animation_interval: float = ANIMATION_INTERVAL_SECONDS,
        concurrent: bool = False,
        live_cases: LiveCases | None = None,
    ) -> None:
        self._output_fn = output_fn
        self._concurrent = concurrent
        self._live_cases = live_cases
        self._llm_activity = llm_activity
        self._active_label: str | None = None
        self._animation_interval = animation_interval
        self._stop_animation = Event()
        self._render_lock = Lock()
        self._animation_thread: Thread | None = None
        self._live_updates = (
            output_fn is builtin_print and sys.stdout.isatty()
            if live_updates is None
            else live_updates
        )

    def __call__(self, event: BenchmarkProgress) -> None:
        if event.stage == 'source_preparation':
            marker, color = {'started': ('RUNNING', ANSI_YELLOW),
                             'succeeded': ('OK', ANSI_GREEN),
                             'failed': ('FAILED', ANSI_RED)}[event.status]
            self._output_fn(f'[{event.agent_id}] {event.detail} .... {color}{marker}{ANSI_RESET}')
            return
        if self._live_cases is not None and event.stage != "sdk_check":
            self._live_cases.on_progress(event)
            return
        if self._concurrent:
            if (event.stage == "case_generation" and getattr(event, "phase", None) == "generate"
                    and event.status == "started" and event.detail):
                identity = case_identity(event.agent_id or "suite")
                self._output_fn(f"{identity} Case generation · {event.detail}")
                return
            identity = case_identity(event.agent_id or "suite", event.case_index, event.job_id)
            stage = event.stage.replace("_", " ").capitalize()
            detail = f" · {event.detail}" if event.detail else ""
            self._output_fn(f"{identity} {stage} · {event.status}{detail}")
            return
        if event.status == "started":
            self._start_stage(_stage_label(event))
            return

        status = "OK" if event.status == "succeeded" else "FAILED"
        color = ANSI_GREEN if event.status == "succeeded" else ANSI_RED
        suffix = f" | {event.detail}" if event.detail else ""
        self._finish_stage(f"{color}{status}{ANSI_RESET}{suffix}")

    def _start_stage(self, label: str) -> None:
        if self._llm_activity is not None:
            self._llm_activity.start_stage(label)
            return
        if not self._live_updates:
            self._output_fn(label)
            return

        self._stop_active_animation()
        self._active_label = label
        self._stop_animation.clear()
        self._animation_thread = Thread(
            target=self._animate_stage,
            args=(label,),
            daemon=True,
        )
        self._animation_thread.start()

    def _finish_stage(self, status: str) -> None:
        if self._llm_activity is not None:
            self._llm_activity.finish_stage(status)
            return
        if not self._live_updates:
            self._output_fn(f"  {status}")
            return

        label = self._active_label or "Stage"
        self._stop_active_animation()
        final_label = f"{_base_stage_label(label)}..."
        with self._render_lock:
            sys.stdout.write(f"\r\033[2K  {final_label} {status}\n")
            sys.stdout.flush()
        self._active_label = None

    def _animate_stage(self, label: str) -> None:
        base_label = _base_stage_label(label)
        frame_index = 0
        while not self._stop_animation.is_set():
            dots = DOT_FRAMES[frame_index % len(DOT_FRAMES)]
            with self._render_lock:
                sys.stdout.write(
                    f"\r\033[2K  {base_label}{dots} {ANSI_YELLOW}RUNNING{ANSI_RESET}"
                )
                sys.stdout.flush()
            frame_index += 1
            self._stop_animation.wait(self._animation_interval)

    def _stop_active_animation(self) -> None:
        if self._animation_thread is None:
            return

        self._stop_animation.set()
        self._animation_thread.join(timeout=self._animation_interval + 0.1)
        self._animation_thread = None

    def close(self) -> None:
        """Stop any live renderer left active by an interrupted run."""

        if self._llm_activity is not None:
            self._llm_activity.close()
            return
        self._stop_active_animation()


def configuration_error(message: object) -> str:
    """Format a fatal suite configuration error."""

    return f"{ANSI_RED}[Configuration error] {message}{ANSI_RESET}"


def _stage_label(event: BenchmarkProgress) -> str:
    if event.stage == "sdk_check":
        return "Checking evaluation SDK configuration..."
    if event.stage == "agent_start":
        return "Starting Agent..."
    if event.stage == "case_generation":
        if event.phase == "generate" and event.detail:
            return f"{event.detail}..."
        return "Generating Case from the selected SDK..."
    return "Running Agent inputs and SDK Judge..."


def _base_stage_label(label: str) -> str:
    return label.rstrip(".")

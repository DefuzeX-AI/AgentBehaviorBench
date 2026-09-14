"""Lifecycle state for one running model interceptor."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from agentbench.runtime.contracts.execution import Deadline, DockerCleanupError


@dataclass(slots=True)
class RunningModelInterceptor:
    container_name: str
    ca_certificate: Path
    _close_callback: Callable[[], None] = field(repr=False)
    _log_process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _closed: bool = field(default=False, repr=False)
    _trace_reader: threading.Thread | None = field(default=None, repr=False)
    _close_with_deadline: Callable[[Deadline | None], None] | None = field(default=None, repr=False)
    _close_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _close_error: DockerCleanupError | None = field(default=None, repr=False)

    def close(self, *, deadline: Deadline | None = None) -> None:
        from agentbench.runtime.docker.command import DockerCommandRunner
        with self._close_lock:
            if self._closed:
                if self._close_error is not None:
                    raise self._close_error
                return
            self._closed = True
            errors: list[str] = []
            # Stop the producer while docker logs still reads; EOF then drains
            # pending trace events before its thread is joined.
            try:
                if self._close_with_deadline is not None:
                    self._close_with_deadline(deadline)
                else:
                    self._close_callback()
            except Exception as exc:
                errors.append(str(exc))
            finally:
                if self._log_process is not None:
                    try:
                        self._log_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            DockerCommandRunner.terminate(self._log_process)
                        except Exception as exc:
                            errors.append(f"Trace Docker client did not exit: {exc}")
                if self._trace_reader is not None:
                    self._trace_reader.join(timeout=2)
                    if self._trace_reader.is_alive():
                        errors.append("Interceptor trace reader did not exit")
            if errors:
                self._close_error = DockerCleanupError("; ".join(errors))
                raise self._close_error

    def __enter__(self) -> "RunningModelInterceptor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

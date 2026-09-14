"""Lifecycle and diagnostic logs for one Agent container, independent of its API."""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TextIO

from agentbench.runtime.contracts.execution import DockerCleanupError, RunControl, RuntimeInfrastructureError
from .command import DockerCommandRunner


class DockerSessionError(RuntimeError):
    """Raised when an Agent container cannot be managed."""


class DockerSession:
    def __init__(
        self, process: subprocess.Popen[str], *,
        close_callback: Callable[[], None],
        trace_checkpoint: Callable[[], object] | None = None,
        trace_validator: Callable[[object], None] | None = None,
        control: RunControl | None = None,
        default_timeout: float = 2400,
        runtime_error_checker: Callable[[], None] | None = None,
    ) -> None:
        self._process = process
        self._stdout: deque[str] = deque(maxlen=100)
        self._stderr: deque[str] = deque(maxlen=100)
        self._log_lock = threading.Lock()
        self._close_callback = close_callback
        self._trace_checkpoint = trace_checkpoint
        self._trace_validator = trace_validator
        self._closed = False
        self._control = control or RunControl()
        self._default_timeout = default_timeout
        self._close_lock = threading.Lock()
        self._close_error: RuntimeInfrastructureError | None = None
        self._runtime_error_checker = runtime_error_checker
        self._readers: list[threading.Thread] = []
        for stream, target, name in (
            (process.stdout, self._stdout, "stdout"),
            (process.stderr, self._stderr, "stderr"),
        ):
            if stream is not None:
                reader = threading.Thread(
                    target=self._read_log, args=(stream, target), daemon=True,
                    name=f"abb-agent-{name}",
                )
                reader.start()
                self._readers.append(reader)

    @property
    def is_running(self) -> bool:
        return not self._closed and self._process.poll() is None

    @property
    def returncode(self) -> int | None:
        return self._process.poll()

    @property
    def stdout(self) -> str:
        with self._log_lock:
            return "".join(self._stdout)

    @property
    def stderr(self) -> str:
        with self._log_lock:
            return "".join(self._stderr)

    def wait(self, timeout: float | None = None) -> int:
        """Wait for process exit; output has no required syntax or response shape."""
        selected_timeout = self._default_timeout if timeout is None else timeout
        deadline = time.monotonic() + selected_timeout
        while True:
            self._control.check()
            if self._runtime_error_checker is not None:
                self._runtime_error_checker()
            code = self._process.poll()
            if code is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired("Docker Agent execution", selected_timeout)
            try:
                code = self._process.wait(timeout=min(0.1, remaining))
                self._control.check()
                break
            except subprocess.TimeoutExpired:
                continue
        for reader in self._readers:
            reader.join(timeout=1)
        if self._runtime_error_checker is not None:
            self._runtime_error_checker()
        return code

    def trace_checkpoint(self) -> object:
        return self._trace_checkpoint() if self._trace_checkpoint else None

    def validate_trace(self, checkpoint: object) -> None:
        if self._trace_validator:
            self._trace_validator(checkpoint)

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                if self._close_error is not None:
                    raise self._close_error
                return
            self._closed = True
            errors: list[str] = []
            try:
                # The real container must stop before its attached CLI client.
                # Keep readers alive while the container flushes final output.
                self._close_callback()
            except Exception as exc:
                errors.append(str(exc))
            finally:
                try:
                    DockerCommandRunner.terminate(self._process)
                except Exception as exc:
                    errors.append(f"Agent Docker client did not exit: {exc}")
                for reader in self._readers:
                    reader.join(timeout=2)
                    if reader.is_alive():
                        errors.append(f"Agent log reader did not exit: {reader.name}")
            if errors:
                self._close_error = DockerCleanupError("; ".join(errors))
                raise self._close_error
            if self._runtime_error_checker is not None:
                try:
                    self._runtime_error_checker()
                except RuntimeInfrastructureError as exc:
                    self._close_error = exc
                    raise

    def _read_log(self, stream: TextIO, target: deque[str]) -> None:
        try:
            for line in stream:
                with self._log_lock:
                    target.append(line[-16384:])
        finally:
            stream.close()

    def __enter__(self) -> "DockerSession":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

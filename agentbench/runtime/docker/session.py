"""Lifecycle and diagnostic logs for one Agent container, independent of its API."""

from __future__ import annotations

import subprocess
import threading
from collections import deque
from collections.abc import Callable
from typing import TextIO


class DockerSessionError(RuntimeError):
    """Raised when an Agent container cannot be managed."""


class DockerSession:
    def __init__(
        self, process: subprocess.Popen[str], *,
        close_callback: Callable[[], None],
        trace_checkpoint: Callable[[], object] | None = None,
        trace_validator: Callable[[object], None] | None = None,
    ) -> None:
        self._process = process
        self._stdout: deque[str] = deque(maxlen=100)
        self._stderr: deque[str] = deque(maxlen=100)
        self._log_lock = threading.Lock()
        self._close_callback = close_callback
        self._trace_checkpoint = trace_checkpoint
        self._trace_validator = trace_validator
        self._closed = False
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
        code = self._process.wait(timeout=timeout)
        for reader in self._readers:
            reader.join(timeout=1)
        return code

    def trace_checkpoint(self) -> object:
        return self._trace_checkpoint() if self._trace_checkpoint else None

    def validate_trace(self, checkpoint: object) -> None:
        if self._trace_validator:
            self._trace_validator(checkpoint)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=5)
        finally:
            try:
                self._close_callback()
            finally:
                for reader in self._readers:
                    reader.join(timeout=1)

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

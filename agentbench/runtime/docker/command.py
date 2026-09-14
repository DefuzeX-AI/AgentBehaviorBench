"""Finite, cancellable Docker CLI calls with file-backed output capture."""

from __future__ import annotations

import subprocess
import tempfile
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from agentbench.runtime.contracts.execution import Deadline, RunControl


class DockerCommandTimeout(TimeoutError):
    """The client was stopped; the Docker daemon may still be doing work."""


class DockerCommandRunner:
    def __init__(self, executable: str = "docker", *, environ: Mapping[str, str] | None = None) -> None:
        self.executable = executable
        self.environ = dict(os.environ if environ is None else environ)

    def start(self, args: Sequence[str], *, control: RunControl | None = None,
              **kwargs) -> subprocess.Popen[str]:
        if control is not None:
            control.check()
        kwargs.setdefault("env", self.environ)
        return subprocess.Popen([self.executable, *args], **kwargs)

    def run(
        self, args: Sequence[str], *, control: RunControl | None = None,
        timeout: float = 60, deadline: Deadline | None = None,
        cleanup: bool = False, log_directory: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        own_deadline = Deadline.after(timeout)
        if deadline is not None:
            own_deadline = Deadline(min(deadline.expires_at, own_deadline.expires_at))
        if not cleanup and control is not None:
            control.check()
        if not own_deadline.remaining():
            raise DockerCommandTimeout("Docker command budget exhausted before launch")
        # Build output can be huge. Keep it out of pipes and Python memory; return
        # only a bounded tail for diagnostics and retain full files when requested.
        if log_directory is not None:
            log_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile() if log_directory is None else tempfile.NamedTemporaryFile(
            dir=log_directory, prefix="docker-", suffix=".stdout.log", delete=False
        ) as stdout, tempfile.TemporaryFile() if log_directory is None else tempfile.NamedTemporaryFile(
            dir=log_directory, prefix="docker-", suffix=".stderr.log", delete=False
        ) as stderr:
            process = self.start(
                args, control=None if cleanup else control,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            )
            try:
                while True:
                    if not cleanup and control is not None:
                        control.check()
                    remaining = own_deadline.remaining()
                    if not remaining:
                        raise DockerCommandTimeout("Docker command timed out; daemon state requires verification")
                    try:
                        code = process.wait(timeout=min(0.1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if not cleanup and control is not None:
                    control.check()
                return subprocess.CompletedProcess(
                    [self.executable, *args], code, _tail(stdout), _tail(stderr)
                )
            except BaseException as exc:
                # Resource owners must distinguish an interrupted live client
                # from cancellation observed after the daemon replied.
                exc.docker_client_interrupted = process.poll() is None
                raise
            finally:
                if process.poll() is None:
                    self.terminate(process)

    @staticmethod
    def terminate(process: subprocess.Popen, *, grace: float = 1) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            process.wait(timeout=2)


def _tail(stream, maximum: int = 2 * 1024 * 1024) -> str:
    size = stream.tell()
    stream.seek(max(0, size - maximum))
    value = stream.read().decode("utf-8", errors="replace")
    return ("[earlier output omitted]\n" if size > maximum else "") + value

"""An operating-system lock held for the complete Suite coordinator lifetime."""

import os
from pathlib import Path

from filelock import FileLock, Timeout


class SuiteLockedError(RuntimeError):
    """Another coordinator currently owns this Suite."""


class SuiteLock:
    def __init__(self, directory: Path):
        self.path = directory / '.writer.lock'
        # Keep the stable lock path and require an OS lock: a crashed process
        # must release ownership without leaving a stale soft-lock marker.
        self._lock = FileLock(self.path, thread_local=False,
                              preserve_lock_file=True, fallback_to_soft=False)
        self._pid = None

    def acquire(self, *, timeout: float = 0) -> None:
        if self._pid is not None:
            self.check()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=timeout)
        except Timeout as exc:
            raise SuiteLockedError(f'Another coordinator already owns this Suite: {self.path}') from exc
        self._pid = os.getpid()

    def check(self) -> None:
        if self._pid != os.getpid() or not self._lock.is_locked:
            raise RuntimeError('Suite mutations require the owning process writer lock')

    def close(self) -> None:
        if self._pid == os.getpid():
            self._lock.release()
        self._pid = None

"""An operating-system lock held for the complete Suite coordinator lifetime."""

import os
from pathlib import Path


class SuiteLockedError(RuntimeError):
    """Another coordinator currently owns this Suite."""


class SuiteLock:
    def __init__(self, directory: Path):
        self.path = directory / '.writer.lock'
        self._stream = None
        self._pid = None

    def acquire(self) -> None:
        if self._stream is not None:
            self.check()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if stream.tell() == 0:
                    stream.write(b'\0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise SuiteLockedError('Another coordinator already owns this Suite') from exc
        self._stream = stream
        self._pid = os.getpid()

    def check(self) -> None:
        if self._stream is None or self._pid != os.getpid():
            raise RuntimeError('Suite mutations require the owning process writer lock')

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            if self._pid == os.getpid():
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

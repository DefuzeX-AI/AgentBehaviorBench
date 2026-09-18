"""Durable atomic file publication used by Suite plans, Cases and events."""

import json
import os
from pathlib import Path
import tempfile
import time


_WINDOWS = os.name == 'nt'
_WINDOWS_REPLACE_ERRORS = {5, 32, 33}  # access denied, sharing violation, lock violation
_REPLACE_ATTEMPTS = 8


def _replace(temporary: Path, path: Path) -> None:
    """Replace a file after brief Windows reader locks have cleared."""
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            retryable = (_WINDOWS
                         and getattr(exc, 'winerror', None) in _WINDOWS_REPLACE_ERRORS
                         and attempt + 1 < _REPLACE_ATTEMPTS)
            if not retryable:
                raise
            time.sleep(min(0.01 * (2 ** attempt), 0.2))


def atomic_bytes(path: Path, content: bytes) -> None:
    """Publish complete bytes and sync the file before replacing its old version."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f'.{path.name}.',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(temporary, path)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False) + '\n').encode('utf-8'))

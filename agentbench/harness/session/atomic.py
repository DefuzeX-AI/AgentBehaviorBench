"""Durable atomic file publication used by Suite plans, Cases and events."""

import json
import os
from pathlib import Path
import tempfile


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
        os.replace(temporary, path)
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

"""Bounded, host-only reads for independently retained ground truth evidence."""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat

JSON_LIMIT = 2 * 1024 * 1024
EVIDENCE_LIMIT = 64 * 1024 * 1024
RECORD_LIMIT = 10000


class GroundTruthError(ValueError):
    """A ground truth record cannot be used as verified benchmark evidence."""


def label(value):
    """Identifiers in diagnostics are labels, never raw file paths or exception text."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(value))[:100]


def within(root, path):
    try:
        root = Path(root).resolve()
        path = Path(path).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise GroundTruthError('path cannot be resolved safely') from error
    if not path.is_relative_to(root):
        raise GroundTruthError('path leaves its permitted directory')
    return path


def read_bytes(path, limit=JSON_LIMIT):
    try:
        with _open_regular(path) as stream:
            before = _regular_stat(stream.fileno())
            data = stream.read(limit + 1)
            if before != _regular_stat(stream.fileno()):
                raise GroundTruthError('file changed while being read')
    except OSError as error:
        raise GroundTruthError('required file is unavailable') from error
    if len(data) > limit:
        raise GroundTruthError('file exceeds the size limit')
    return data


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GroundTruthError('JSON contains duplicate keys')
        result[key] = value
    return result


def read_json(path, *, limit=JSON_LIMIT):
    try:
        value = json.loads(read_bytes(path, limit=limit), object_pairs_hook=_unique_keys,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except GroundTruthError:
        raise
    except (ValueError, UnicodeError, RecursionError) as error:
        raise GroundTruthError('invalid JSON document') from error
    if not isinstance(value, dict):
        raise GroundTruthError('document must be a JSON object')
    return value


def _regular_stat(path_or_fd):
    try:
        info = os.fstat(path_or_fd) if isinstance(path_or_fd, int) else Path(path_or_fd).stat()
    except OSError as error:
        raise GroundTruthError('required file is unavailable') from error
    if not stat.S_ISREG(info.st_mode):
        raise GroundTruthError('evidence and manifests must be regular files')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _open_regular(path):
    _regular_stat(path)
    # O_NONBLOCK also prevents a file swapped for a FIFO between stat/open from
    # stalling the viewer. Validate the descriptor before consuming any bytes.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        _regular_stat(stream.fileno())
        yield stream


def text_field(record, name):
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GroundTruthError(f'{name} must be a nonempty string')
    return value


def timestamp_field(record, name):
    value = text_field(record, name)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
    except ValueError as error:
        raise GroundTruthError(f'{name} must include an ISO 8601 timezone') from error
    return value


def records_field(document, name):
    value = document.get(name)
    if not isinstance(value, list) or len(value) > RECORD_LIMIT or any(not isinstance(row, dict) for row in value):
        raise GroundTruthError(f'{name} must be a bounded list of objects')
    return value

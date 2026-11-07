"""Hash-only final workspace evidence for the local Judge.

The host calls this after the isolated Agent has stopped but before its temporary
workspace is removed. No file contents are sent to the Judge. Sensitive paths,
linked entries, secrets and unreadable or oversized files are omitted explicitly;
an incomplete snapshot can never silently become complete evidence.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import stat
from collections import Counter

from agentbench.observe.store import environment_secrets, redact
from agentbench.sdk.common.artifacts import Artifacts

MAX_FILES = 10000
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


def _sensitive_path(relative):
    for part in Path(relative).parts:
        name = part.lower()
        if (name in ('.git', '.kuma', 'id_rsa', 'id_ed25519', 'credentials.json', 'secrets.json')
                or name.startswith('.env') or name.endswith(('.pem', '.key', '.p12', '.pfx'))):
            return True
    return False


def _open_regular(root, relative):
    """Open each component without following links, including a replaced parent."""
    parts = Path(relative).parts
    if not parts or any(part in ('', '.', '..') for part in parts):
        raise ValueError('Invalid workspace evidence path')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    parent = os.open(root, flags | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(parts[-1], flags, dir_fd=parent)
    finally:
        os.close(parent)
    return fd


def capture_workspace(root, destination, policy, *, environ=None):
    """Save independent final file names, sizes and hashes without file contents."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not policy.path:
        raise ValueError('Workspace evidence requires a valid workspace')
    secrets = tuple(v.encode('utf-8') for v in environment_secrets(environ) if v)
    records, omitted = [], 0
    reasons = Counter()
    total = 0
    def mark(reason):
        nonlocal omitted
        omitted += 1
        reasons[reason] += 1
    def onerror(_):
        mark('unreadable_directory')
    for current, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        current = Path(current)
        keep = []
        for name in sorted(dirs):
            child = current / name
            relative = child.relative_to(root).as_posix()
            if child.is_symlink():
                mark('linked_directory')
            elif _sensitive_path(relative) or redact(relative, environment_secrets(environ)) != relative:
                mark('sensitive_path')
            else:
                keep.append(name)
        dirs[:] = keep
        for name in sorted(files):
            path = current / name; relative = path.relative_to(root).as_posix()
            if len(records) + omitted >= MAX_FILES:
                mark('file_count_limit'); dirs[:] = []; break
            if _sensitive_path(relative) or redact(relative, environment_secrets(environ)) != relative:
                mark('sensitive_path'); continue
            try:
                fd = _open_regular(root, relative)
                with os.fdopen(fd, 'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                        mark('non_regular_or_hard_link'); continue
                    if before.st_size > MAX_FILE_BYTES:
                        mark('file_size_limit'); continue
                    if total + before.st_size > MAX_TOTAL_BYTES:
                        mark('total_size_limit'); continue
                    data = stream.read(MAX_FILE_BYTES + 1)
                    after = os.fstat(stream.fileno())
                    if (len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino)
                            != (after.st_size, after.st_mtime_ns, after.st_ino)):
                        mark('changed_during_capture'); continue
                    if any(secret in data for secret in secrets):
                        mark('sensitive_content'); continue
                total += len(data)
                records.append({'path': relative, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            except (OSError, ValueError):
                mark('unreadable_or_linked_file')
    records.sort(key=lambda item: item['path'])
    result = {'schema': 'abb.local.workspace-evidence.v1',
              'capture_point': 'after_agent_cleanup_before_workspace_deletion',
              'workspace': policy.path, 'initial_state': policy.initial_state,
              'status': 'partial' if omitted else 'complete', 'files': records, 'omitted_count': omitted,
              'omitted_reasons': dict(sorted(reasons.items()))}
    Artifacts(destination, environ=environ).save('local-workspace-evidence.json', result)
    return result

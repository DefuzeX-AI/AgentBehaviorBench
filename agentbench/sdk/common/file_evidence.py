"""Bounded, read-only workspace observations for the independent SDK worker.

Snapshots describe observed state at input boundaries, not atomic filesystem
transactions or proof of every tool action. Omitted content stays an explicit
evidence gap. No KUMA import, workspace writes, or private replay upload occurs.
"""
import difflib
import hashlib
import itertools
import os
from pathlib import Path
import re
import stat

from agentbench.observe.store import redact


SENSITIVE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~-]{12,}|"
    r"\b(?:sk-|oc_sk_|dfx_)[A-Za-z0-9_-]{16,}|"
    r"[\"']?(?:api[_-]?key|password|access[_-]?token|secret)[\"']?\s*[:=]\s*[\"']?[^\s\"',}]{8,}",
    re.IGNORECASE,
)


class FileEvidence:
    def __init__(self, root, *, secrets=(), max_file_bytes=256 * 1024,
                 max_total_bytes=8 * 1024 * 1024, max_entries=1000):
        self.root = Path(root)
        self.secrets = tuple(secrets)
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_entries = max_entries

    def capture(self):
        entries, errors = {}, []
        total = visited = 0
        nofollow = getattr(os, 'O_NOFOLLOW', 0)
        directory = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | nofollow

        def omit(relative, reason, **metadata):
            entries[relative] = {**metadata, 'omitted': reason}

        def walk(fd, prefix=''):
            nonlocal total, visited
            with os.scandir(fd) as stream:
                names = sorted(itertools.islice(stream, self.max_entries + 1), key=lambda e: e.name)
            for item in names:
                visited += 1
                if visited > self.max_entries:
                    errors.append('entry_limit')
                    return
                if item.name in {'.git', '.kuma'}:
                    continue
                relative = prefix + item.name
                try:
                    info = os.stat(item.name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        omit(relative, 'linked_path')
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(item.name, directory, dir_fd=fd)
                        try:
                            walk(child, relative + '/')
                        finally:
                            os.close(child)
                    elif not stat.S_ISREG(info.st_mode):
                        omit(relative, 'non_regular_file')
                    elif (SENSITIVE.search(relative) or redact(relative, self.secrets) != relative
                          or item.name == '.env' or item.name.startswith('.env.')
                          or Path(item.name).suffix.lower() in {'.key', '.pem'}):
                        omit(relative, 'sensitive_content')
                    elif info.st_size > self.max_file_bytes:
                        omit(relative, 'file_size_limit', size_bytes=info.st_size)
                    elif total + info.st_size > self.max_total_bytes:
                        omit(relative, 'total_size_limit', size_bytes=info.st_size)
                    else:
                        handle = os.open(item.name, os.O_RDONLY | nofollow | getattr(os, 'O_NONBLOCK', 0), dir_fd=fd)
                        with os.fdopen(handle, 'rb') as stream:
                            before = os.fstat(stream.fileno())
                            if not stat.S_ISREG(before.st_mode):
                                omit(relative, 'non_regular_file')
                                continue
                            data = stream.read(self.max_file_bytes + 1)
                            after = os.fstat(stream.fileno())
                        if ((before.st_ino, before.st_mtime_ns, before.st_size)
                                != (after.st_ino, after.st_mtime_ns, after.st_size)
                                or len(data) != after.st_size or len(data) > self.max_file_bytes):
                            omit(relative, 'changed_during_capture')
                            continue
                        if total + len(data) > self.max_total_bytes:
                            omit(relative, 'total_size_limit', size_bytes=len(data))
                            continue
                        total += len(data)
                        try:
                            text = data.decode('utf-8')
                        except UnicodeDecodeError:
                            omit(relative, 'binary_content')
                            continue
                        if '\0' in text:
                            omit(relative, 'binary_content')
                            continue
                        if SENSITIVE.search(text) or redact(text, self.secrets) != text:
                            omit(relative, 'sensitive_content')
                            continue
                        entries[relative] = {'sha256': hashlib.sha256(data).hexdigest(),
                                             'size_bytes': len(data), 'content': text}
                except OSError:
                    omit(relative, 'unreadable_or_changed_path')

        try:
            fd = os.open(self.root, directory)
            try:
                walk(fd)
            finally:
                os.close(fd)
        except OSError:
            errors.append('workspace_unreadable')
        complete = not errors and not any('omitted' in e for e in entries.values())
        return {'status': 'complete' if complete else 'partial', 'entries': entries, 'errors': errors}

    def publish(self, before, after, files, prefix, *, export, diff):
        changes = []

        def public_path(name):
            if SENSITIVE.search(name) or redact(name, self.secrets) != name:
                return '[omitted_sensitive_path]'
            return name

        def state(entry, side):
            value = {k: v for k, v in entry.items() if k != 'content'}
            if export and 'content' in entry:
                artifact = f'{prefix}/file-content/{side}-{entry["sha256"]}.json'
                files.save(artifact, {'encoding': 'utf-8', 'content': entry['content']})
                value['artifact'] = artifact
            return value

        for name in sorted(set(before['entries']) | set(after['entries'])):
            a, b = before['entries'].get(name), after['entries'].get(name)
            if a == b:
                continue
            row = {'path': public_path(name), 'change_type': 'created' if a is None else 'deleted' if b is None else 'modified',
                   'before': state(a, 'before') if a is not None else None,
                   'after': state(b, 'after') if b is not None else None}
            if diff and (a is None or 'content' in a) and (b is None or 'content' in b):
                row['diff'] = ''.join(difflib.unified_diff(
                    (a or {}).get('content', '').splitlines(keepends=True),
                    (b or {}).get('content', '').splitlines(keepends=True),
                    fromfile='before/' + name, tofile='after/' + name))
            changes.append(row)
        manifest = {'schema': 'abb.file-evidence.v1',
                    'status': 'complete' if before['status'] == after['status'] == 'complete' else 'partial',
                    'time_basis': 'observed_input_boundaries',
                    'before': {k: v for k, v in before.items() if k != 'entries'},
                    'after': {k: v for k, v in after.items() if k != 'entries'},
                    'omissions': {side: [{'path': public_path(name), 'reason': row['omitted']}
                                         for name, row in snap['entries'].items() if 'omitted' in row]
                                  for side, snap in [('before', before), ('after', after)]},
                    'changes': changes}
        files.save(prefix + '/file-evidence.json', manifest)
        return manifest

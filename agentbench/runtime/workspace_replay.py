"""Local workspace versions. No SDK imports, trace emission, or upload hooks."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import sys
import threading
import time

REPLAY_MOUNT = '/run/abb-replay'
EXCLUDED = {'.git', '.kuma'}
MAX_FILES = 10000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_EVENTS = 100000
MAX_METADATA_BYTES = 32 * 1024 * 1024


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


class DirectoryNotifications:
    """Linux directory notifications; periodic reconciliation remains authoritative."""
    def __init__(self, root):
        self.root, self.fd, self.watched = root, -1, set()
        if sys.platform == 'linux':
            self.libc = ctypes.CDLL(None, use_errno=True)
            self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)

    def refresh(self, directories):
        if self.fd < 0:
            return
        for directory in directories:
            if directory not in self.watched:
                # Writes, attributes, moves, creation/deletion; never follow links.
                wd = self.libc.inotify_add_watch(self.fd, os.fsencode(directory),
                                               0x00000fce | 0x01000000 | 0x02000000)
                if wd >= 0:
                    self.watched.add(directory)

    def changed(self):
        if self.fd < 0 or not select.select([self.fd], [], [], 0)[0]:
            return False
        # Events only trigger a reconciliation; paths/timestamps are not claimed
        # to describe every individual write. Overflow also triggers a full scan.
        while True:
            try:
                os.read(self.fd, 65536)
            except BlockingIOError:
                break
        return True

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class WorkspaceRecorder:
    """Capture observed versions with explicit gaps and bounded content storage.

    A timestamp is the observation time, never an inferred tool operation time.
    Boundary snapshots and notifications share a lock; published blobs precede
    events. The destination must be outside the entire observed workspace.
    """
    def __init__(self, root, destination, *, secrets=(), interval=0.25,
                 max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_BYTES):
        self.root = Path(root).resolve(strict=True)
        self.destination = Path(destination).resolve()
        if self.destination == self.root or self.destination.is_relative_to(self.root):
            raise ValueError('Replay storage must be outside the observed workspace')
        if not self.root.is_dir():
            raise ValueError('Replay workspace is not a directory')
        self.destination.mkdir(parents=True, exist_ok=True)
        if any((self.destination / name).exists() for name in ('baseline.json', 'events.jsonl', 'manifest.json')):
            raise FileExistsError('An existing replay archive must not be overwritten')
        (self.destination / 'blobs').mkdir(exist_ok=True)
        self.secrets = tuple(s for s in secrets if isinstance(s, str) and s)
        self.interval = interval
        self.max_file_bytes, self.max_total_bytes = max_file_bytes, max_total_bytes
        self.entries, self.signatures, self.errors = {}, {}, set()
        self.bytes = self.sequence = self.event_bytes = 0
        self.exhausted = False
        self.lock, self.stop_event = threading.Lock(), threading.Event()
        self.watcher = DirectoryNotifications(self.root)
        self.thread = None
        self.started = time.time_ns() / 1e6
        self.status = 'recording'
        try:
            self.capture('baseline', force=True)
        except BaseException:
            self.watcher.close()
            raise
        self.thread = threading.Thread(target=self._watch, name='abb-workspace-replay', daemon=True)
        self.thread.start()

    def _save(self, name, value):
        path = self.destination / name
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')
        temporary.replace(path)

    def _manifest(self):
        self._save('manifest.json', {
            'schema': 'abb.workspace-replay.v1', 'status': self.status,
            'workspace': str(self.root), 'started_ms': self.started,
            'updated_ms': time.time_ns() / 1e6, 'event_count': self.sequence,
            'content_bytes': self.bytes, 'local_only': True,
            'capture_mode': 'notifications_with_reconciliation' if self.watcher.fd >= 0 else 'sampled',
            'poll_interval_ms': self.interval * 1000,
            'time_basis': 'observed', 'excluded_directories': sorted(EXCLUDED),
            'limits': {'files': MAX_FILES, 'file_bytes': self.max_file_bytes,
                       'total_bytes': self.max_total_bytes, 'events': MAX_EVENTS,
                       'event_bytes': MAX_METADATA_BYTES},
            'omitted_content_count': sum(bool(e.get('omitted')) for e in self.entries.values()),
            'warnings': sorted(self.errors),
        })

    def _content(self, path, relative, info):
        entry = {'type': 'file', 'size': info.st_size, 'mode': stat.S_IMODE(info.st_mode)}
        if path.name == '.env' or path.name.startswith('.env.') or path.suffix.lower() in {'.pem', '.key'}:
            return {**entry, 'omitted': 'sensitive_path'}
        if info.st_size > self.max_file_bytes:
            return {**entry, 'omitted': 'file_size_limit'}
        # Check each ancestor immediately before opening; O_NOFOLLOW also rejects
        # a file replaced with a symlink between lstat and open on Linux.
        current = self.root
        for part in Path(relative).parts:
            current = current / part
            if linked(current.lstat()):
                raise OSError('Linked path')
        if not path.resolve(strict=True).is_relative_to(self.root):
            raise OSError('Path outside workspace')
        descriptor = self._open(relative)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return {**entry, 'omitted': 'non_regular_file'}
            data = stream.read(self.max_file_bytes + 1)
            after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise OSError('File changed during capture')
        if len(data) > self.max_file_bytes:
            return {**entry, 'omitted': 'file_size_limit'}
        redacted = False
        try:
            text = data.decode('utf-8')
            for secret in self.secrets:
                text = text.replace(secret, '[REDACTED]')
            safe = text.encode('utf-8')
            redacted = safe != data
            data = safe
        except UnicodeDecodeError:
            # Binary files retain metadata; do not persist unscannable content.
            return {**entry, 'omitted': 'binary_content'}
        if b'\0' in data:
            return {**entry, 'omitted': 'binary_content'}
        digest = hashlib.sha256(data).hexdigest()
        blob = self.destination / 'blobs' / digest
        if not blob.exists():
            if self.bytes + len(data) > self.max_total_bytes:
                self.errors.add('Content storage limit reached; some versions contain metadata only.')
                return {**entry, 'omitted': 'storage_limit'}
            temporary = blob.with_suffix('.tmp')
            temporary.write_bytes(data)
            temporary.replace(blob)
            self.bytes += len(data)
        return {**entry, 'blob': digest, 'redacted': redacted}

    def _open(self, relative, *, directory=False):
        """Linux openat traversal prevents ancestor-symlink replacement races."""
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        if sys.platform != 'linux':
            return os.open(self.root / relative, flags)
        parent = os.open(self.root, flags | os.O_DIRECTORY)
        parts = Path(relative).parts
        try:
            for part in parts[:-1]:
                child = os.open(part, flags | os.O_DIRECTORY, dir_fd=parent)
                os.close(parent)
                parent = child
            if not parts:
                return os.dup(parent)
            return os.open(parts[-1], flags | (os.O_DIRECTORY if directory else 0), dir_fd=parent)
        finally:
            os.close(parent)

    def capture(self, reason, *, input_id=None, force=False):
        with self.lock:
            if self.sequence >= MAX_EVENTS or self.exhausted:
                self.errors.add('Event storage limit reached; further file changes were not recorded.')
                self._manifest()
                return
            entries, signatures, directories = {}, {}, [self.root]
            failed = False
            def scan(directory):
                nonlocal failed
                descriptor = None
                try:
                    if sys.platform == 'linux':
                        descriptor = self._open(directory.relative_to(self.root), directory=True)
                    with os.scandir(descriptor if descriptor is not None else directory) as children:
                        for child in children:
                            if child.name in EXCLUDED:
                                continue
                            if len(entries) >= MAX_FILES:
                                failed = True
                                self.errors.add('File count limit reached; workspace coverage is partial.')
                                return
                            path = directory / child.name
                            relative = path.relative_to(self.root).as_posix()
                            try:
                                info = child.stat(follow_symlinks=False)
                                if linked(info):
                                    entries[relative] = {'type': 'link', 'omitted': 'link_not_followed'}
                                elif stat.S_ISDIR(info.st_mode):
                                    entries[relative] = {'type': 'directory'}
                                    directories.append(path)
                                    scan(path)
                                elif stat.S_ISREG(info.st_mode):
                                    signature = (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_mode)
                                    if not force and self.signatures.get(relative) == signature:
                                        entries[relative] = self.entries[relative]
                                    else:
                                        entries[relative] = self._content(path, relative, info)
                                    signatures[relative] = signature
                                else:
                                    entries[relative] = {'type': 'special', 'omitted': 'non_regular_file'}
                            except FileNotFoundError:
                                continue
                            except OSError:
                                failed = True
                                self.errors.add('Some paths could not be read consistently; previous versions may be stale.')
                except OSError:
                    failed = True
                    self.errors.add('A directory could not be scanned; previous versions may be stale.')
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
            scan(self.root)
            if failed:
                # An unreadable directory is not proof that its children vanished.
                entries = dict(list({**self.entries, **entries}.items())[:MAX_FILES])
            self.watcher.refresh(directories)
            changes = [{'path': name, 'before': self.entries.get(name), 'after': entries.get(name)}
                       for name in sorted(self.entries.keys() | entries.keys())
                       if self.entries.get(name) != entries.get(name)]
            now = time.time_ns() / 1e6
            if reason == 'baseline':
                self._save('baseline.json', {'time_ms': now, 'entries': entries})
            elif changes or reason != 'change':
                event = {'sequence': self.sequence + 1, 'time_ms': now, 'reason': reason,
                         'input_id': input_id, 'changes': changes, 'partial': failed}
                encoded = json.dumps(event, ensure_ascii=True) + '\n'
                if self.event_bytes + len(encoded) > MAX_METADATA_BYTES:
                    self.exhausted = True
                    self.errors.add('Event storage limit reached; further file changes were not recorded.')
                    self._manifest()
                    return
                with (self.destination / 'events.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(encoded)
                self.sequence += 1
                self.event_bytes += len(encoded)
            self.entries, self.signatures = entries, signatures
            self._manifest()

    def _watch(self):
        last = time.monotonic()
        while not self.stop_event.wait(self.interval):
            try:
                if self.watcher.changed() or self.watcher.fd < 0 or time.monotonic() - last >= 2:
                    self.capture('change')
                    last = time.monotonic()
            except Exception:
                self.errors.add('Background capture failed; replay coverage is partial.')

    def finish(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join()
        try:
            self.capture('final', force=True)
            self.status = 'partial' if self.errors else 'complete'
            self._manifest()
        finally:
            self.watcher.close()

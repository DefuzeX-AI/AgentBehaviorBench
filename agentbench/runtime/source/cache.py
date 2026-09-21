"""Commit-addressed archives with OS locks and atomic publication."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import time
import zipfile

from .git import export_source


@contextmanager
def cache_lock(path, check):
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        while True:
            check()
            try:
                if os.name == 'nt':
                    import msvcrt
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def source_archive(spec, directory, check, output_fn=lambda text: None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((spec.repository + '\n' + spec.revision).encode()).hexdigest()
    target = directory / (key + '.zip')
    with cache_lock(directory / (key + '.lock'), check):
        if target.is_file():
            output_fn('Source cache: verifying')
            with zipfile.ZipFile(target) as archive:
                if archive.comment.decode('ascii') != spec.revision or archive.testzip() is not None:
                    raise ValueError('Source cache is corrupt; remove ' + str(target))
            output_fn('Source cache: reused verified archive .... OK')
            return target
        with tempfile.TemporaryDirectory(prefix='.download-', dir=directory) as temporary:
            staged = Path(temporary) / 'source.zip'
            output_fn('Downloading source: ' + spec.repository + ' @ ' + spec.revision)
            export_source(spec, staged, check)
            with zipfile.ZipFile(staged) as archive:
                if archive.comment.decode('ascii') != spec.revision or archive.testzip() is not None:
                    raise ValueError('Invalid downloaded source archive')
            check()
            os.replace(staged, target)
            output_fn('Downloading source: commit verified and cached .... OK')
    return target

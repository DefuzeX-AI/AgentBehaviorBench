"""Bounded, link-safe copying of Agent-produced directories."""
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .context import ResponseLimits


@contextmanager
def _open_entry(path, *, parent=None, directory=False):
    if os.name == 'nt':
        import _winapi
        import msvcrt
        # OPEN_REPARSE_POINT opens the link itself. FILE_SHARE_READ denies writes
        # and renames while this entry and all its ancestors are being visited.
        handle = _winapi.CreateFile(str(path), 0x80000000, 1, 0, 3, 0x02200000, 0)
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _winapi.CloseHandle(handle)
            raise
    else:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path if parent is None else path.name,
                     flags | (os.O_DIRECTORY if directory else 0), dir_fd=parent)
    try:
        info = os.fstat(fd)
        if getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Agent response contains a reparse point')
        if directory and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Expected an Agent response directory')
        yield fd, info
    finally:
        os.close(fd)


def collect_response(source, destination, *, limits=None):
    limits = limits or ResponseLimits()
    total, count = 0, 0

    def visit(fd, relative):
        nonlocal total, count
        for name in os.listdir(source / relative if os.name == 'nt' else fd):
            count += 1
            if count > limits.max_files:
                raise ValueError(f'Agent response exceeds file transport limit ({limits.max_files})')
            current = relative / name
            if current.parts[0] in ('done.json', 'input.json', 'request.json',
                                    'context.json', 'mapped-input.json'):
                continue
            with _open_entry(source / current, parent=fd) as (handle, info):
                if stat.S_ISDIR(info.st_mode):
                    visit(handle, current)
                elif stat.S_ISREG(info.st_mode):
                    def byte_limit():
                        return ValueError('Agent response exceeds transport byte limit '
                                          f'({limits.max_bytes} bytes; file {current})')
                    if total + info.st_size > limits.max_bytes:
                        raise byte_limit()
                    target = destination / current
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Publish only complete files, even if a producer grows a
                    # response after fstat or the copy encounters an I/O error.
                    stream = tempfile.NamedTemporaryFile(dir=target.parent, delete=False)
                    temporary = Path(stream.name)
                    try:
                        with stream:
                            while block := os.read(handle, 65536):
                                total += len(block)
                                if total > limits.max_bytes:
                                    raise byte_limit()
                                stream.write(block)
                        temporary.replace(target)
                    finally:
                        temporary.unlink(missing_ok=True)
                else:
                    raise ValueError('Agent response contains a special file')

    with _open_entry(source, directory=True) as (fd, _):
        visit(fd, Path())

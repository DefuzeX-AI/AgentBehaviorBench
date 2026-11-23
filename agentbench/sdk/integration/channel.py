"""Bounded, link-safe copying of Agent-produced directories."""
import tempfile
from pathlib import Path

from .context import ResponseLimits

def collect_response(source, destination, *, limits=None):
    # All reads are relative to held directory descriptors. O_NOFOLLOW and
    # O_NONBLOCK reject symlink swaps and FIFOs created by an Agent, including
    # while copying. This client runs in the Linux controller container.
    import os
    import stat
    limits = limits or ResponseLimits()
    total, count = 0, 0
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

    def visit(fd, relative):
        nonlocal total, count
        for name in os.listdir(fd):
            count += 1
            if count > limits.max_files:
                raise ValueError(f'Agent response exceeds file transport limit ({limits.max_files})')
            current = relative / name
            if current.parts[0] in ('done.json', 'input.json', 'request.json',
                                    'context.json', 'mapped-input.json'):
                continue
            handle = os.open(name, flags, dir_fd=fd)
            try:
                info = os.fstat(handle)
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
            finally:
                os.close(handle)

    fd = os.open(source, flags | os.O_DIRECTORY)
    try:
        visit(fd, Path())
    finally:
        os.close(fd)

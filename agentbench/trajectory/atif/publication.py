"""Atomic directory publication without replacing another export."""
import ctypes
import errno
import os


def publish_directory(source, destination):
    if os.name == "nt":
        # Windows rename refuses an existing destination, including directories.
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    encoded_source, encoded_destination = os.fsencode(source), os.fsencode(destination)
    if hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        with_parent = os.open(source.parent, os.O_RDONLY)
        try:
            result = function(with_parent, os.fsencode(source.name), with_parent, os.fsencode(destination.name), 1)  # RENAME_NOREPLACE
        finally:
            os.close(with_parent)
    elif hasattr(libc, "renamex_np"):
        function = libc.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = function(encoded_source, encoded_destination, 4)  # RENAME_EXCL
    else:
        raise OSError(errno.ENOTSUP, "Atomic no-replace publication is unavailable")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))

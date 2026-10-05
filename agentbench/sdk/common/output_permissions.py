"""Publish container-owned artifacts through the explicit output mount."""
import os
import stat
from pathlib import Path


def prepare_output(directory):
    """Create shared output and Judge directories under a private host Run.

    The container exports Judge context here, then the host atomically writes
    the report. Both UIDs need directory write access; the containing Run is
    host-owned and 0700. Creating these directories on the host retains host
    ownership through the worker's read-only permission publication.
    """
    root = Path(directory)
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    judge = root / 'judge'
    judge.mkdir(mode=0o777)
    judge.chmod(0o777)
    return root


def share_output(directory):
    """Allow host reads without changing identity, contents or write permissions.

    The host's private run directory (0700) protects this mount. Atomic SDK
    writes use 0600, so the image's native UID must publish them before exit.
    Never follow symlinks or chmod files belonging to another UID.
    """
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        return
    for parent, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories
                          if not (Path(parent) / name).is_symlink()]
        for path in (Path(parent), *(Path(parent) / name for name in files)):
            info = path.lstat()
            if info.st_uid != os.getuid():
                continue
            if stat.S_ISDIR(info.st_mode):
                path.chmod(stat.S_IMODE(info.st_mode) | 0o055)
            elif stat.S_ISREG(info.st_mode):
                path.chmod(stat.S_IMODE(info.st_mode) | 0o044)

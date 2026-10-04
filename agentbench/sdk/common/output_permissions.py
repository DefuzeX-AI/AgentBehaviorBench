"""Publish container-owned artifacts through the explicit output mount."""
import os
import stat
from pathlib import Path


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

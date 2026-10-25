"""Runtime permission unmasking for ABB container environments."""
import os
import atexit
import tempfile
from pathlib import Path

os.umask(0)


def _open_paths():
    for base in ("/run/abb-channel", "/run/abb-channel/response", "/run/abb-channel/request", "/run/abb-output"):
        p = Path(base)
        if p.exists():
            try:
                os.chmod(p, 0o777)
            except OSError:
                pass
            for root, dirs, files in os.walk(p):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o777)
                    except OSError:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o666)
                    except OSError:
                        pass


_open_paths()
atexit.register(_open_paths)

_orig_mkdir = os.mkdir


def _permissive_mkdir(path, mode=0o777):
    _orig_mkdir(path, mode)
    try:
        os.chmod(path, 0o777)
    except OSError:
        pass


os.mkdir = _permissive_mkdir

_orig_named_temp = tempfile.NamedTemporaryFile


def _permissive_named_temp(*args, **kwargs):
    f = _orig_named_temp(*args, **kwargs)
    try:
        os.chmod(f.name, 0o666)
    except OSError:
        pass
    return f


tempfile.NamedTemporaryFile = _permissive_named_temp

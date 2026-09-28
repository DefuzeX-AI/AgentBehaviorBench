from __future__ import annotations

import sysconfig
import warnings
from pathlib import Path


def _find_tablegpt_ipykernel_profile_dir():
    # https://docs.python.org/3.11/library/sysconfig.html#sysconfig.get_path
    # https://docs.python.org/3.11/library/sysconfig.html#user-scheme
    _py_root = Path(sysconfig.get_path("data"))

    possible_profile_dir = Path(_py_root, "share", "ipykernel", "profile", "tablegpt")

    _startup_folder = Path(possible_profile_dir, "startup")
    try:
        if next(_startup_folder.glob(r"*-udfs.py")):
            return str(possible_profile_dir)
    except StopIteration:
        return


DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR: str | None = _find_tablegpt_ipykernel_profile_dir()

if DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR is None:
    msg = """Unable to find tablegpt ipykernel. If you need to use a local kernel,
please use `pip install -U tablegpt-agent[local]` to install the necessary dependencies.
For more issues, please submit an issue to us https://github.com/tablegpt/tablegpt-agent/issues."""
    warnings.warn(msg, stacklevel=2)

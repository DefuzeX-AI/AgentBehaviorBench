"""Locate the ABB project directory: where registries, env files, results and viewer assets live."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT_ENV = "ABB_PROJECT_ROOT"


def project_root() -> Path:
    """Return the directory project-relative CLI defaults resolve against.

    ``ABB_PROJECT_ROOT`` wins when set. A source checkout -- this package next to
    ``pyproject.toml`` and ``resources/`` -- keeps its own root, as before. An
    installed package has neither beside it: ``Path(__file__).parents`` then
    points into site-packages, which holds no registry, env file or results, so
    the current working directory is the project, as for any installed CLI.
    """
    override = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[1]
    if (checkout / "pyproject.toml").is_file() and (checkout / "resources").is_dir():
        return checkout
    return Path.cwd().resolve()

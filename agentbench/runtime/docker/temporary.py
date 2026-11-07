"""Private host directories for interceptor files bind-mounted into Docker."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path


def interceptor_temp_directory(environ: Mapping[str, str]) -> Path:
    """Prefer a VM-shared macOS location without changing global tempfile state."""
    configured = environ.get("ABB_DOCKER_TMPDIR", "").strip()
    parent = None
    if configured:
        parent = Path(configured).expanduser()
        if not parent.is_absolute():
            raise ValueError("ABB_DOCKER_TMPDIR must be an absolute directory shared with Docker")
    elif sys.platform == "darwin":
        # Colima shares the user's home by default, but not macOS /private/var.
        parent = Path.home() / ".cache" / "agentbench" / "docker"

    try:
        if parent is not None:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # mkdtemp creates a unique, owner-only directory for each interceptor.
        return Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-", dir=parent))
    except OSError as exc:
        raise OSError(
            "Cannot create model interceptor temporary directory; set ABB_DOCKER_TMPDIR "
            "to a writable absolute directory shared with Docker"
        ) from exc

"""Save one validated file atomically, without replacing existing user content."""

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from .errors import BuildError
from .paths import file_path


def confined(root: Path, name: str) -> Path:
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()) or any(
        parent.is_symlink() for parent in (target, *target.parents)
        if parent.is_relative_to(root)
    ):
        raise BuildError("Onboarding destination contains a symlink or escapes the unit")
    return target


def start_attempt(records: Path) -> Path:
    directory = confined(records, uuid4().hex)
    directory.mkdir(parents=True)
    return directory


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_file(unit: Path, name: str, content: str) -> Path:
    """Install one complete file with an exclusive link; never undo previous steps.

    A temporary file is fully flushed before linking it into the destination.
    os.link fails atomically if the destination already exists, including a
    concurrently created file. Interruption cannot leave a half-written output.
    """
    path = confined(unit, file_path(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".agent-build-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(stream.fileno(), 0o644)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path

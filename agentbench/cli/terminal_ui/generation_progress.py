"""Read the SDK's live Case collection for honest terminal progress."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

_MAX_COLLECTION_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class GenerationProgress:
    total: int
    active_index: int | None
    ready: int
    failed: int


def read_generation_progress(data: Mapping[str, object]) -> GenerationProgress | None:
    """Read only the small, SDK-written collection for a generation trace event."""
    if data.get("phase") != "generate":
        return None
    directory = data.get("artifact_directory")
    if not isinstance(directory, str) or not directory:
        return None
    root = Path(directory)
    evaluation = root / "evaluation"
    path = evaluation / "case-collection.json"
    try:
        if evaluation.is_symlink() or path.is_symlink():
            return None
        with path.open("rb") as stream:
            raw = stream.read(_MAX_COLLECTION_BYTES + 1)
        if len(raw) > _MAX_COLLECTION_BYTES:
            return None
        collection = json.loads(raw)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(collection, dict):
        return None
    total = collection.get("requested_count")
    active = collection.get("active_case_index")
    cases = collection.get("cases")
    failures = collection.get("failures")
    if (type(total) is not int or total < 1 or not isinstance(cases, list)
            or not isinstance(failures, list)):
        return None
    if active is not None and (type(active) is not int or not 0 <= active < total):
        return None
    return GenerationProgress(total, active, len(cases), len(failures))

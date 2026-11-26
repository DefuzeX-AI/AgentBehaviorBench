"""Reviewer marks written straight into a saved ``trajectory.atif.json``.

A reviewer marks a step with a reason, and the mark is added to that step's
``extra.abb.marks`` in the saved document at once. There is no other copy: the
trajectory file is the only record of its marks. A step is named by its
trajectory ID and step ID, both fixed once the document is saved. Deriving the
trajectory again replaces the file and therefore drops its marks.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_REASON = 4000
_lock = threading.Lock()


def _trajectories(document):
    pending = [document]
    while pending:
        trajectory = pending.pop(0)
        yield trajectory
        pending.extend(trajectory.get("subagent_trajectories") or [])


def _step(document, trajectory_id, step_id):
    for trajectory in _trajectories(document):
        if trajectory.get("trajectory_id") != trajectory_id:
            continue
        for step in trajectory.get("steps") or []:
            if step.get("step_id") == step_id:
                return step
    raise KeyError(f"No step {step_id} in trajectory {trajectory_id}")


def _edit(directory, change):
    """Apply ``change(document)`` to the saved trajectory; return its new SHA-256."""
    from harbor.models.trajectories import Trajectory
    from .attempt import FILENAME
    from .export import save_json
    path = Path(directory) / FILENAME
    with _lock:
        if not path.is_file():
            raise FileNotFoundError(f"No saved trajectory to mark: {path}")
        document = json.loads(path.read_text(encoding="utf-8"))
        change(document)
        Trajectory.model_validate(document)
        save_json(path, document)
        return hashlib.sha256(path.read_bytes()).hexdigest()


def add(directory, trajectory_id, step_id, reason):
    """Add one mark to a step; return ``(mark, sha256)``."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A mark needs a reason")
    if len(reason) > MAX_REASON:
        raise ValueError(f"A mark reason is limited to {MAX_REASON} characters")
    mark = {"reason": reason.strip(), "created_at": datetime.now(timezone.utc).isoformat()}

    def change(document):
        step = _step(document, trajectory_id, step_id)
        abb = step.setdefault("extra", {}).setdefault("abb", {})
        abb.setdefault("marks", []).append(mark)
    return mark, _edit(directory, change)


def remove(directory, trajectory_id, step_id, created_at):
    """Remove the step's mark recorded at ``created_at``; return the new SHA-256."""
    def change(document):
        step = _step(document, trajectory_id, step_id)
        abb = (step.get("extra") or {}).get("abb") or {}
        marks = abb.get("marks") or []
        kept = [mark for mark in marks if mark.get("created_at") != created_at]
        if len(kept) == len(marks):
            raise KeyError(f"No mark at {created_at} on step {step_id}")
        if kept:
            abb["marks"] = kept
        else:
            abb.pop("marks")
            if not abb:
                step["extra"].pop("abb")
            if not step["extra"]:
                step.pop("extra")
    return _edit(directory, change)

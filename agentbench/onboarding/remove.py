"""Remove one Agent unit: drop its registry entry and archive its folder.

Nothing is permanently erased. The unit folder moves into cache/agent-trash under
the registry's repository root, and only the matching [[agents]] block is removed
from the registry text, so other entries and their formatting are preserved.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentbench.harness.registry import tomllib
from agentbench.harness.session.locking import SuiteLock

# FILE_ATTRIBUTE_REPARSE_POINT: Windows junctions are not reported by is_symlink().
_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class RemovalPlan:
    target: str
    agents_directory: Path
    registry_path: Path
    archive_root: Path
    agent_id: str | None  # None when the folder was imported but never registered.
    unit: Path | None  # None when the registered folder is already missing.


def plan_removal(target: str, *, agents_directory: Path, registry_path: Path) -> RemovalPlan:
    """Resolve a registered agent_id or a numbered folder name without changing files."""
    registry = Path(registry_path).absolute()
    if registry.is_symlink():
        raise ValueError("Registry path must not be a symlink")
    root = registry.parent.parent.resolve()
    agents = Path(agents_directory).resolve()
    if not agents.is_dir():
        raise ValueError(f"Agent directory does not exist: {agents}")

    name = target if _plain_name(target) else None
    entries = _registry_entries(registry)
    matches = [
        entry for entry in entries
        if entry.get("agent_id") == target
        or (name is not None and isinstance(entry.get("path"), str)
            and (root / entry["path"]).resolve() == agents / name)
    ]
    if len(matches) > 1:
        raise ValueError(f"{target!r} matches more than one registry entry")
    if matches:
        agent_id, relative = matches[0].get("agent_id"), matches[0].get("path")
        if not isinstance(agent_id, str) or not isinstance(relative, str):
            raise ValueError(f"Registry entry for {target!r} needs string agent_id and path")
        folder = root / relative
    elif name is not None and (agents / name).is_dir():
        agent_id, folder = None, agents / name
    else:
        raise ValueError(f"No registered Agent or folder named {target!r} in {agents}")

    unit = folder if folder.exists() or folder.is_symlink() else None
    if unit is not None:
        if _linked(unit) or not unit.is_dir():
            raise ValueError(f"Refusing to delete a symlink, junction or non-directory: {unit}")
        if unit.resolve().parent != agents:
            raise ValueError(f"{unit} is not directly inside {agents}; pass the matching --agents-dir")
    return RemovalPlan(target, agents, registry, root / "cache" / "agent-trash", agent_id, unit)


def apply_removal(plan: RemovalPlan) -> Path | None:
    """Archive the folder, then remove the registry entry; return the archived folder.

    The registry is replaced last. If that fails, the folder is moved back.
    """
    lock_directory = plan.registry_path.parent / ".agent-add-lock"
    if lock_directory.is_symlink():
        raise ValueError("Onboarding lock directory must not be a symlink")
    lock = SuiteLock(lock_directory)
    lock.acquire()
    try:
        current = plan_removal(plan.target, agents_directory=plan.agents_directory,
                               registry_path=plan.registry_path)
        if current != plan:
            raise ValueError("The Agent or registry changed after preview; run delete again")
        original = replacement = None
        if plan.agent_id is not None:
            original = plan.registry_path.read_text(encoding="utf-8")
            replacement = _temporary_registry(plan.registry_path,
                                              _without_entry(original, plan.agent_id))
        archived = None
        try:
            if plan.unit is not None:
                archived = _archive(plan.unit, plan.archive_root)
            if replacement is not None:
                if plan.registry_path.read_text(encoding="utf-8") != original:
                    raise RuntimeError("Registry changed during deletion; nothing was removed")
                replacement.replace(plan.registry_path)
        except BaseException:
            if archived is not None:
                _restore(archived, plan.unit)
            raise
        finally:
            if replacement is not None:
                replacement.unlink(missing_ok=True)
        return archived
    finally:
        lock.close()


def _registry_entries(registry: Path) -> list[dict]:
    if not registry.exists():
        return []
    entries = tomllib.loads(registry.read_text(encoding="utf-8")).get("agents", [])
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise ValueError(f"Registry agents must be a list of tables: {registry}")
    return entries


def _without_entry(text: str, agent_id: str) -> str:
    """Remove exactly one [[agents]] block and prove nothing else changed."""
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.strip() == "[[agents]]"]
    kept = lines[:starts[0]] if starts else lines
    removed = 0
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        rows = tomllib.loads("".join(lines[start:end])).get("agents", [])
        if len(rows) == 1 and rows[0].get("agent_id") == agent_id:
            removed += 1
            continue
        kept.extend(lines[start:end])
    result = "".join(kept).rstrip("\n") + "\n"
    before, after = tomllib.loads(text), tomllib.loads(result)
    expected = dict(before, agents=[entry for entry in before.get("agents", [])
                                    if entry.get("agent_id") != agent_id])
    if removed != 1 or dict(after, agents=after.get("agents", [])) != expected:
        raise ValueError(f"Cannot remove {agent_id} without changing other registry content; "
                         "edit the registry manually")
    return result


def _temporary_registry(registry: Path, text: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=registry.parent,
                                     prefix=".registry-delete-", suffix=".toml",
                                     delete=False) as stream:
        stream.write(text)
    return Path(stream.name)


def _archive(unit: Path, trash: Path) -> Path:
    for directory in (trash.parent, trash):
        if directory.is_symlink():
            raise ValueError(f"Refusing to archive into a symlinked directory: {directory}")
        directory.mkdir(exist_ok=True)
    batch = trash / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex)
    batch.mkdir(mode=0o700)
    archived = batch / unit.name
    try:
        unit.rename(archived)
    except OSError:
        batch.rmdir()
        raise
    return archived


def _restore(archived: Path, unit: Path) -> None:
    try:
        archived.rename(unit)
    except OSError as exc:
        raise RuntimeError(f"Deletion failed and the folder could not be moved back; "
                           f"recover it from {archived}") from exc
    try:
        archived.parent.rmdir()
    except OSError:
        pass  # An empty timestamped archive directory is harmless.


def _plain_name(value: str) -> bool:
    return (value not in ("", ".", "..") and Path(value).name == value
            and not any(character in value for character in "/\\:"))


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & _REPARSE_POINT)

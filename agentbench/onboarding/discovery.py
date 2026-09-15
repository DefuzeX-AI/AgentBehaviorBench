"""Find setup documents and declared LangGraph entrypoints without importing code."""

from __future__ import annotations

import json
import os
from fnmatch import fnmatchcase
from pathlib import Path


SKIPPED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next",
})
FILE_PATTERNS = (
    "*langgraph*.json", "pyproject.toml", "uv.lock", "poetry.lock", "pdm.lock",
    "requirements*.txt", "requirements*.in", "constraints*.txt", "setup.py", "setup.cfg",
    "pipfile", "pipfile.lock", "environment.yml", "environment.yaml",
    "dockerfile", "dockerfile.*", "*.dockerfile", ".dockerignore",
    "docker-compose*.yml", "docker-compose*.yaml", "compose.yml", "compose.yaml",
    "readme", "readme.*", ".env.example", ".env.sample", ".env.template",
    ".env.*.example", ".python-version", "runtime.txt",
)


def discover_files(source_root: Path) -> tuple[str, ...]:
    """Return sorted POSIX paths to files useful for an Agent's initial scan.

    Args:
        source_root: Downloaded repository root, not the outer numbered unit.
    Returns:
        Unique paths relative to source_root, including existing Python files
        referenced by LangGraph configs. Malformed configs are still listed.

    This only reads filenames and LangGraph JSON; it never imports Agent code,
    reads actual .env files, or follows symlinks.
    """
    root = source_root.resolve(strict=True)
    found: set[str] = set()
    for directory, directories, filenames in os.walk(root, followlinks=False):
        folder = Path(directory)
        directories[:] = sorted(name for name in directories
                                if name not in SKIPPED_DIRECTORIES
                                and not (folder / name).is_symlink())
        for name in sorted(filenames):
            path = folder / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            requirement = ("requirements" in relative.parts[:-1]
                           and path.suffix.lower() in {".txt", ".in"})
            if not requirement and not any(fnmatchcase(name.lower(), pattern) for pattern in FILE_PATTERNS):
                continue
            found.add(relative.as_posix())
            if fnmatchcase(name.lower(), "*langgraph*.json"):
                found.update(_entrypoint_files(path, root))
    return tuple(sorted(found))


def _entrypoint_files(config: Path, root: Path) -> set[str]:
    if config.stat().st_size > 1024 * 1024:
        return set()
    try:
        value = json.loads(config.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        return set()
    graphs = value.get("graphs") if isinstance(value, dict) else None
    if not isinstance(graphs, dict):
        return set()
    result = set()
    for entry in graphs.values():
        reference = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(reference, str):
            continue
        filename, separator, attribute = reference.rpartition(":")
        if not separator or not attribute or not filename.endswith(".py"):
            continue
        candidate = Path(os.path.abspath(config.parent / filename))
        if not candidate.is_relative_to(root):
            continue
        relative = candidate.relative_to(root)
        if any(part in SKIPPED_DIRECTORIES for part in relative.parts):
            continue
        if any(parent.is_symlink() for parent in (candidate, *candidate.parents)
               if parent.is_relative_to(root)):
            continue
        if candidate.is_file():
            result.add(relative.as_posix())
    return result

"""Collect bounded source evidence using filenames and ASTs, never imports."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

from ...discovery import SKIPPED_DIRECTORIES
from ...source import DownloadedAgent
from .privacy import redact
from .settings import BuildSettings
from .lock_context import read_lock_excerpt
from .javascript_context import references


def safe_file(root: Path, name: str) -> Path | None:
    """Resolve an existing regular file without traversing symlinks or secrets."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    if any(part in SKIPPED_DIRECTORIES for part in relative.parts):
        return None
    path = root / relative
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(root)):
        return None
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return None
    lower = path.name.lower()
    if lower.startswith(".env") and not lower.endswith((".example", ".sample", ".template")):
        return None
    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return None
    return path


def collect_context(source: DownloadedAgent, settings: BuildSettings,
                    environ: Mapping[str, str]) -> dict:
    """Return source evidence, byte counts and omissions suitable for a model prompt.

    Inputs are a downloaded unit, explicit size budgets and a secret-redaction
    environment. Output contains relative paths and text, never environment values.
    Entry-point dependencies are followed statically; repository code is not run.
    """
    root = source.directory / "agent"
    queue = sorted(source.files, key=_priority)
    seen, files, omitted = set(), [], []
    used = 0
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        path = safe_file(root, name)
        if path is None or path.name == "package-lock.json":
            omitted.append({"path": name, "reason": "excluded"})
            continue
        remaining = min(settings.max_file_bytes, settings.max_context_bytes - used)
        if len(files) >= settings.max_files or remaining <= 0:
            omitted.append({"path": name, "reason": "context_budget"})
            continue
        try:
            if path.suffix.lower() == ".lock":
                content, truncated = read_lock_excerpt(path, remaining)
            else:
                with path.open("rb") as stream:
                    raw = stream.read(remaining + 1)
                truncated = len(raw) > remaining
                content = raw[:remaining].decode("utf-8-sig", errors="strict")
        except UnicodeError:
            omitted.append({"path": name, "reason": "non_utf8_or_truncated_character"})
            continue
        if "\0" in content:
            omitted.append({"path": name, "reason": "binary"})
            continue
        original_content = content
        if path.name.startswith(".env"):
            # Examples can contain real credentials: expose names only.
            content = "\n".join(line.split("=", 1)[0].strip() + "=<set in host environment>"
                                for line in content.splitlines()
                                if "=" in line and not line.lstrip().startswith("#"))
        content = redact(content, environ)
        encoded = content.encode("utf-8")
        if len(encoded) > remaining:
            content = encoded[:remaining].decode("utf-8", errors="ignore")
            truncated = True
        used += len(content.encode("utf-8"))
        entry = {"path": name, "build_context_path": "agent/" + name,
                 "content": content, "truncated": truncated}
        if path.suffix.lower() == ".lock" and truncated:
            entry["excerpt"] = "Bounded lockfile excerpt; omitted content may contain additional constraints."
        files.append(entry)
        if path.suffix == ".py" and not truncated:
            queue[0:0] = _imports(root, path, original_content)
        elif not truncated:
            queue[0:0] = references(root, path, original_content)
    return {"repository": source.repository, "revision": source.revision,
            "source_root": "agent/", "file_paths_relative_to": "agent/",
            "files": files, "omitted": omitted, "content_bytes": used}


def _priority(name: str) -> tuple:
    path = Path(name)
    name = path.name.lower()
    rank = (0 if "langgraph" in name or "acp" in name else 1 if path.suffix in {".py", ".ts"} else
            2 if path.suffix.lower() == ".lock" or name.startswith("requirements") or name in
            {"pyproject.toml", "setup.cfg", ".python-version", "runtime.txt"} else
            4 if name.startswith("readme.") and name not in {"readme.md", "readme.rst", "readme.txt"} else 3)
    return rank, len(path.parts), name


def _imports(root: Path, path: Path, content: str) -> list[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    candidates = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules, bases = [alias.name for alias in node.names], (root, root / "src")
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            modules = [prefix, *(f"{prefix}.{alias.name}".strip(".") for alias in node.names)]
            base = path.parent
            for _ in range(max(0, node.level - 1)):
                base = base.parent
            bases = (base,) if node.level else (root, root / "src", path.parent)
        else:
            continue
        for base in bases:
            for module in modules:
                target = base.joinpath(*module.split("."))
                for candidate in (target.with_suffix(".py"), target / "__init__.py"):
                    if candidate.is_relative_to(root):
                        name = candidate.relative_to(root).as_posix()
                        if safe_file(root, name):
                            candidates.add(name)
    return sorted(candidates)

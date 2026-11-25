"""Find setup documents and declared LangGraph entrypoints without importing code."""

from __future__ import annotations

import json
import os
import re
from fnmatch import fnmatchcase
from pathlib import Path


SKIPPED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next",
})
FILE_PATTERNS = (
    "*langgraph*.json", "pyproject.toml", "uv.lock", "poetry.lock", "pdm.lock", "dependencies.lock",
    "requirements*.txt", "requirements*.in", "constraints*.txt", "setup.py", "setup.cfg",
    "pipfile", "pipfile.lock", "environment.yml", "environment.yaml",
    # Dockerfile, Dockerfile.dev, DockerfileDev, Dockerfile_cpu_base; compose.mongo.yaml.
    "dockerfile*", "*.dockerfile", ".dockerignore", "docker-compose*.y*ml", "compose*.y*ml",
    # README.md, README_CN.md, README-ja_JP.md; .env.example, .env-example, ".env example".
    "readme*", ".env*example*", ".env*sample*", ".env*template*",
    ".python-version", "runtime.txt", ".nvmrc", ".tool-versions",
    # Non-Python build inputs: a Node front end or MCP server, a Go or Rust component, make targets.
    "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "yarn.lock",
    "*acp*.ts", "*acp*.py", "*acp*.rs", "*acp*.go", "cli.ts", "index.ts", "tsconfig*.json",
    "main.rs", "main.go",
    "go.mod", "cargo.toml", "makefile",
    "application.py", "app.py", "main.py", "__main__.py",
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
            elif name.lower() == "pyproject.toml":
                found.update(_python_entrypoint_files(path, root))
    return tuple(sorted(found))


def _python_entrypoint_files(config: Path, root: Path) -> set[str]:
    """Resolve declared installed CLI modules statically; never import packages."""
    from agentbench.runtime.agentcontainer.config import tomllib

    if config.stat().st_size > 1024 * 1024:
        return set()
    try:
        value = tomllib.loads(config.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        return set()
    project = value.get("project", {})
    if not isinstance(project, dict):
        return set()
    result = set()
    for group in ("scripts", "gui-scripts"):
        declarations = project.get(group, {})
        if not isinstance(declarations, dict):
            continue
        for reference in declarations.values():
            if not isinstance(reference, str):
                continue
            module, separator, attribute = reference.partition(":")
            if not separator or not attribute or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
                continue
            for base in (config.parent, config.parent / "src"):
                target = base.joinpath(*module.split("."))
                for path in (target.with_suffix(".py"), target / "__init__.py"):
                    if not path.is_relative_to(root) or not path.is_file():
                        continue
                    relative = path.relative_to(root)
                    if any(part in SKIPPED_DIRECTORIES for part in relative.parts):
                        continue
                    if any(parent.is_symlink() for parent in (path, *path.parents)
                           if parent.is_relative_to(root)):
                        continue
                    result.add(relative.as_posix())
    return result


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


# Runtime of the Agent's own process, in selection order. A compiled executable precedes
# the package.json that may only distribute it; Bun precedes the Node manifest it shares.
#   runtime: (files identifying it, files declaring its dependencies,
#             declaration of an OTLP trace exporter, automatic profile)
_JAVA_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")
_PYTHON_FILES = ("pyproject.toml", "requirements.txt", "setup.py")
_NODE_EXPORTER = r"@opentelemetry/(sdk-node|auto-instrumentations-node|exporter-trace-otlp-)"
_RUNTIMES = {
    "rust": (("Cargo.toml",), ("Cargo.toml",), r"opentelemetry[-_]otlp", None),
    "go": (("go.mod",), ("go.mod",), r"go\.opentelemetry\.io/otel/exporters/otlp/otlptrace", None),
    "java": (_JAVA_FILES, _JAVA_FILES, r"opentelemetry-exporter-otlp", "java-auto"),
    "bun": (("bun.lock", "bun.lockb", "bunfig.toml"), ("package.json",), _NODE_EXPORTER, None),
    "node": (("package.json",), ("package.json",), _NODE_EXPORTER, "node-auto"),
    "python": (_PYTHON_FILES, _PYTHON_FILES, r"opentelemetry[-_]exporter[-_]otlp", "python-auto"),
}
_EXECUTABLES = {"node": "node", "nodejs": "node", "java": "java", "bun": "bun"}


def _build_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _build_table(path: Path) -> dict:
    """Parse package.json or pyproject.toml; {} when absent, oversized or malformed."""
    from agentbench.runtime.agentcontainer.config import tomllib
    try:
        value = (json if path.suffix == ".json" else tomllib).loads(_build_text(path))
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _table(value, *keys) -> dict:
    """Follow nested table keys, returning {} wherever the declared shape differs."""
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, dict) else {}


def _declared_dependencies(path: Path) -> str:
    """Return one build file's direct runtime dependency declarations as text."""
    if path.name == "package.json":
        package = _build_table(path)
        return "\n".join([*_table(package, "dependencies"), *_table(package, "optionalDependencies")])
    if path.name == "pyproject.toml":
        project = _build_table(path)
        direct = _table(project, "project").get("dependencies")
        direct = [item for item in direct if isinstance(item, str)] if isinstance(direct, list) else []
        return "\n".join([*direct, *_table(project, "tool", "poetry", "dependencies")])
    if path.name == "go.mod":
        return "\n".join(line for line in _build_text(path).splitlines() if "// indirect" not in line)
    return _build_text(path)


def _identifies(runtime: str, folder: Path, command: bool) -> bool:
    """Whether a folder's build files name this runtime; `command` also requires an installed command."""
    package = _build_table(folder / "package.json")
    present = any((folder / name).is_file() and not (folder / name).is_symlink() for name in _RUNTIMES[runtime][0])
    if runtime == "bun":
        # A package may name Bun as its engine or package manager without committing a lockfile.
        present = present or "bun" in _table(package, "engines") or str(package.get("packageManager", "")).startswith("bun@")
    if not present or not command:
        return present
    if runtime in ("bun", "node"):
        return bool(package.get("bin"))
    if runtime == "python":
        project = _build_table(folder / "pyproject.toml")
        return bool(_table(project, "project", "scripts") or _table(project, "tool", "poetry", "scripts"))
    return True


def _runtime_folders(folders, *, command=False) -> dict[str, list[Path]]:
    """Map each runtime, in selection order, to the given folders that identify it."""
    found = {runtime: [folder for folder in folders if _identifies(runtime, folder, command)] for runtime in _RUNTIMES}
    return {runtime: matched for runtime, matched in found.items() if matched}


def discover_otel(adapter, source, framework):
    """Select the target's own OTLP exporter when declared, else its runtime's instrumentor.

    Args:
        adapter: Rendered adapter table; an ACP command names the launched executable.
        source: Downloaded repository root.
        framework: Registered framework name.
    Returns:
        The manifest's [otel] table. `reason` cites the evidence for every selection
        that a Case-level otel/status.json may need to explain.

    This reads dependency declarations only. A declared exporter is not proof that the
    target starts it: a real run's otel/status.json remains the verification.
    """
    root = Path(source)
    command = adapter.get("command") or []
    executable = Path(command[0]).name if command else ""
    if executable == "copilot":
        return {"profile": "native-otlp", "enable_env": {"COPILOT_OTEL_ENABLED": "true"}}
    # A LangGraph binding always runs in the Python worker. An ACP launcher is usually a
    # Python wrapper, so only a direct runtime executable identifies the target by itself.
    acp = framework != "langgraph"
    # Build files at the source root identify the target; a monorepo keeps them one level
    # below, where a Node or Python manifest counts only if it installs a command: a
    # nested SDK or front end is not the Agent.
    children = sorted(path for path in root.iterdir() if path.is_dir() and not path.is_symlink()
                      and path.name not in SKIPPED_DIRECTORIES) if root.is_dir() else []
    found = _runtime_folders([root]) or _runtime_folders(children, command=acp)
    runtime = (_EXECUTABLES.get(executable) or next(iter(found), None)) if acp else "python"
    if runtime is None:
        return {"profile": "unconfigured", "reason": "No build file identifies the runtime of the target executable"}
    _, declarations, exporter, automatic = _RUNTIMES[runtime]
    declared = {path.relative_to(root).as_posix(): _declared_dependencies(path)
                for folder in found.get(runtime) or _runtime_folders(children).get(runtime) or [root]
                for path in (folder / name for name in declarations)}
    for name, text in declared.items():
        if re.search(exporter, text, re.IGNORECASE):
            return {"profile": "native-otlp", "reason": f"OTLP trace exporter declared in {name}"}
    notes = []
    if acp and runtime == "python" and not re.search(r"langchain|langgraph", "\n".join(declared.values()), re.IGNORECASE):
        notes.append("python-auto instruments LangChain only and none is declared")
    # Bun shares package.json with Node, so that pair is one runtime, never an alternative.
    others = sorted(set(found) - {runtime, "node" if runtime == "bun" else runtime}) if acp else []
    if others:
        notes.append(f"source also contains {', '.join(others)}")
    if automatic is None:
        return {"profile": "unsupported", "reason": "; ".join(
            [f"No automatic instrumentation for a {runtime} executable", *notes])}
    return {"profile": automatic, **({"reason": "; ".join([f"Selected for a {runtime} source", *notes])} if notes else {})}

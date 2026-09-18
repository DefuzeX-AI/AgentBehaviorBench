"""Import a GitHub repository or absolute local directory into an Agent unit."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .discovery import discover_files
from .source_status import checkout_warnings


NUMBERED_UNIT = re.compile(r"^(\d+)-(.+)$")


class AgentDownloadError(ValueError):
    """A source URL, destination or Git operation could not be used."""


@dataclass(frozen=True)
class DownloadedAgent:
    directory: Path
    repository: str
    revision: str
    files: tuple[str, ...]
    # Problems found in a successful download that a later build would hit.
    warnings: tuple[str, ...] = ()
    source_type: str = "github"


@dataclass(frozen=True)
class _AgentSource:
    identifier: str
    slug: str
    source_type: str
    directory: Path | None = None


def download_agent(repository: str, agents_directory: Path, *, timeout: float = 300) -> DownloadedAgent:
    """Import source and list its setup files, without registering a runnable Agent.

    Args:
        repository: HTTPS GitHub repository URL or an absolute local directory.
        agents_directory: Parent of numbered units, normally resources/agents.
        timeout: Maximum seconds for each Git command.
    Returns:
        The new unit directory, canonical URL, checked-out commit and scan paths.
    Raises:
        AgentDownloadError: Invalid source, existing unit, failed copy/clone or timeout.
        OSError: The destination cannot be created or written.

    Import and scanning finish in a temporary directory before reserving a
    number. A failed import never leaves a partially imported numbered unit.
    A unit is named NN-repository, or NN-owner-repository when another
    repository already uses that name. Submodules are fetched over HTTPS; ones
    that cannot be are recorded and reported, as are symlinks, which the Docker
    build context refuses.
    """
    selected = _agent_source(repository)
    root = agents_directory.resolve()
    if (selected.directory is not None
            and (root == selected.directory or root.is_relative_to(selected.directory))):
        raise AgentDownloadError(
            "Agent destination cannot be inside the local source directory"
        )
    root.mkdir(parents=True, exist_ok=True)
    _unit_slug(root, selected.identifier, selected.slug)
    with tempfile.TemporaryDirectory(prefix=".agent-add-", dir=root) as temporary:
        stage = Path(temporary)
        source = stage / "agent"
        if selected.directory is None:
            _git(["clone", "--depth", "1", "--", selected.identifier, str(source)], timeout)
            revision = _git(["-C", str(source), "rev-parse", "HEAD"], timeout).strip()
            submodules, warnings = _submodules(source, timeout)
            _remove_tree(source / ".git")
            for module in submodules:
                gitlink = source / module["path"] / ".git"
                if gitlink.is_file() or gitlink.is_symlink():
                    gitlink.unlink()
        else:
            shutil.copytree(
                selected.directory,
                source,
                symlinks=True,
                copy_function=shutil.copy2,
                ignore=lambda _directory, names: {".git"}.intersection(names),
            )
            revision = _tree_revision(source)
            submodules, warnings = [], []
        files = discover_files(source)
        warnings += checkout_warnings(source, submodules)
        metadata = {
            "schema_version": "abb.agent-source.v1",
            "repository": selected.identifier,
            "revision": revision,
            "downloaded_on": datetime.now(timezone.utc).date().isoformat(),
            "source_type": selected.source_type,
        }
        if submodules:
            metadata["submodules"] = submodules
        manifest = stage / "source-manifest.json"
        manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        unit = _reserve_directory(root, selected.identifier, selected.slug)
        try:
            source.rename(unit / "agent")
            manifest.rename(unit / manifest.name)
        except BaseException:
            shutil.rmtree(unit)
            raise
    return DownloadedAgent(
        unit, selected.identifier, revision, files, tuple(warnings), selected.source_type
    )


def _agent_source(value: str, *, require_local: bool = True) -> _AgentSource:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if require_local and not resolved.exists():
            raise AgentDownloadError(f"Local Agent source does not exist: {resolved}")
        if require_local and not resolved.is_dir():
            raise AgentDownloadError(f"Local Agent source is not a directory: {resolved}")
        slug = _slug(resolved.name)
        if not slug:
            raise AgentDownloadError("Local Agent directory name must contain a letter or number")
        return _AgentSource(str(resolved), slug, "local-directory", resolved)
    if "://" not in value:
        raise AgentDownloadError(
            "Use an HTTPS GitHub repository URL or an existing absolute directory"
        )
    url, slug = _github_source(value)
    return _AgentSource(url, slug, "github")


def _github_source(repository: str) -> tuple[str, str]:
    try:
        value = urlsplit(repository)
    except ValueError as exc:
        raise AgentDownloadError("Invalid GitHub repository URL") from exc
    if value.scheme != "https" or value.netloc.lower() != "github.com":
        raise AgentDownloadError("Use an HTTPS GitHub repository URL: https://github.com/owner/repository")
    # GitHub's own "?tab=readme-ov-file" only selects a page tab; any other query or a
    # fragment may carry data (such as a token), so it is refused rather than dropped.
    if value.fragment or (value.query and not re.fullmatch(r"tab=[A-Za-z0-9_-]+", value.query)):
        raise AgentDownloadError("Remove the query string or fragment from the repository URL: "
                                 "https://github.com/owner/repository")
    parts = value.path.strip("/").split("/")
    if len(parts) != 2:
        raise AgentDownloadError("Expected a repository URL, not a GitHub file or branch URL: "
                                 "https://github.com/owner/repository")
    if not re.fullmatch(r"[A-Za-z0-9-]+", parts[0]):
        raise AgentDownloadError(f"Invalid GitHub owner {parts[0]!r}: use letters, digits and hyphens")
    name = parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
        raise AgentDownloadError("Invalid GitHub repository name")
    slug = _slug(name)
    if not slug:
        raise AgentDownloadError("Repository name must contain a letter or number")
    return f"https://github.com/{parts[0]}/{name}", slug


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _unit_slug(root: Path, url: str, slug: str) -> str:
    """Return the unit name for url: its repository name, unless another repository has it.

    Same-named projects by different owners are different Agents; only the same
    repository, or a unit whose repository is unrecorded, is a duplicate.
    """
    local = not url.startswith("https://github.com/")
    owner = url.split("/")[3] if not local else Path(url).parent.name
    owner_slug = f"{_slug(owner) or 'local'}-{slug}"
    occupied: dict[str, tuple[Path, str | None]] = {}
    for path in root.iterdir():
        match = NUMBERED_UNIT.fullmatch(path.name)
        if not match:
            continue
        recorded = _recorded_repository(path)
        if recorded is not None and _same_source(recorded, url, local=local):
            raise AgentDownloadError(f"Agent directory already exists: {path}")
        occupied[match[2].lower()] = (path, recorded)
    for candidate in (slug, owner_slug):
        if candidate not in occupied:
            return candidate
        path, recorded = occupied[candidate]
        if recorded is None:
            raise AgentDownloadError(f"Agent directory already exists: {path}")
    if local:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        candidate = f"{owner_slug}-{digest}"
        if candidate not in occupied:
            return candidate
    path, recorded = occupied[owner_slug]
    raise AgentDownloadError(f"Agent directory name is used by {recorded}: {path}")


def _same_source(recorded: str, requested: str, *, local: bool) -> bool:
    if local:
        return os.path.normcase(recorded) == os.path.normcase(requested)
    return recorded.casefold() == requested.casefold()


def _recorded_repository(unit: Path) -> str | None:
    manifest = unit / "source-manifest.json"
    try:
        repository = json.loads(manifest.read_text(encoding="utf-8")).get("repository")
    except (OSError, ValueError, AttributeError):
        return None
    return repository if isinstance(repository, str) and not manifest.is_symlink() else None


def _reserve_directory(root: Path, url: str, slug: str) -> Path:
    while True:
        name = _unit_slug(root, url, slug)
        numbers = [int(match[1]) for path in root.iterdir()
                   if (match := NUMBERED_UNIT.fullmatch(path.name))]
        number = max(numbers, default=0) + 1
        path = root / f"{number:02d}-{name}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path


def _submodules(source: Path, timeout: float) -> tuple[list[dict], list[str]]:
    """Fetch declared submodules over HTTPS and record what each path holds."""
    if not (source / ".gitmodules").is_file():
        return [], []
    warnings = []
    try:
        # Only HTTPS: no SSH prompts or keys, and no local or file-protocol submodules.
        # GitHub SSH spellings of public submodules are fetched over HTTPS instead.
        _git(["-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
              "-c", "url.https://github.com/.insteadOf=git@github.com:",
              "-c", "url.https://github.com/.insteadOf=ssh://git@github.com/",
              "-C", str(source), "submodule", "update", "--init", "--recursive", "--depth", "1"], timeout)
    except AgentDownloadError as exc:
        warnings.append(f"Some submodules could not be fetched: {exc}")
    try:
        status = _git(["-C", str(source), "submodule", "status", "--recursive"], timeout)
    except AgentDownloadError as exc:
        return [], [*warnings, f"Submodules are declared but their state could not be read: {exc}"]
    submodules = []
    for line in status.splitlines():
        # "<state><commit> <path>[ (<describe>)]"; state "-" means not initialised.
        revision, _, path = line[1:].partition(" ")
        submodules.append({"path": path.rsplit(" (", 1)[0].strip(), "revision": revision,
                           "initialized": line[:1] != "-"})
    return submodules, warnings


def _tree_revision(source: Path) -> str:
    """Return a stable digest for the exact local snapshot copied into the unit."""
    digest = hashlib.sha256()
    for directory, directories, filenames in os.walk(source, followlinks=False):
        directories.sort()
        filenames.sort()
        folder = Path(directory)
        for name in directories:
            path = folder / name
            relative = path.relative_to(source).as_posix().encode("utf-8")
            digest.update(b"path\0" + relative + b"\0")
            if path.is_symlink():
                digest.update(b"link\0" + os.readlink(path).encode("utf-8") + b"\0")
            else:
                digest.update(b"directory\0")
        for name in filenames:
            path = folder / name
            relative = path.relative_to(source).as_posix().encode("utf-8")
            digest.update(b"path\0" + relative + b"\0")
            if path.is_symlink():
                digest.update(b"link\0" + os.readlink(path).encode("utf-8") + b"\0")
                continue
            digest.update(b"file\0")
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _remove_tree(path: Path) -> None:
    """Remove cloned Git metadata, including read-only pack files on Windows."""
    def writable_remove(function, value, _error):
        os.chmod(value, 0o700)
        function(value)

    shutil.rmtree(path, onerror=writable_remove)



def _git(arguments: list[str], timeout: float) -> str:
    try:
        process = subprocess.run(
            ["git", "-c", "core.hooksPath=", *arguments],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise AgentDownloadError("Git is required to download an Agent") from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentDownloadError(f"Git operation timed out after {timeout:g} seconds") from exc
    if process.returncode:
        detail = (process.stderr or process.stdout).strip()[-2000:]
        raise AgentDownloadError(f"Git operation failed: {detail}")
    return process.stdout

"""Download a GitHub repository into the existing NN-name/agent unit layout."""

from __future__ import annotations

import json
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


def download_agent(repository: str, agents_directory: Path, *, timeout: float = 300) -> DownloadedAgent:
    """Download source and list its setup files, without registering a runnable Agent.

    Args:
        repository: HTTPS GitHub owner/repository URL, optionally ending in .git.
        agents_directory: Parent of numbered units, normally resources/agents.
        timeout: Maximum seconds for each Git command.
    Returns:
        The new unit directory, canonical URL, checked-out commit and scan paths.
    Raises:
        AgentDownloadError: Invalid URL, existing unit, failed clone or timeout.
        OSError: The destination cannot be created or written.

    Checkout and scanning finish in a temporary directory before reserving a
    number. A failed download never leaves a partially downloaded numbered unit.
    A unit is named NN-repository, or NN-owner-repository when another
    repository already uses that name. Submodules are fetched over HTTPS; ones
    that cannot be are recorded and reported, as are symlinks, which the Docker
    build context refuses.
    """
    url, slug = _github_source(repository)
    root = agents_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    _unit_slug(root, url, slug)
    with tempfile.TemporaryDirectory(prefix=".agent-add-", dir=root) as temporary:
        stage = Path(temporary)
        source = stage / "agent"
        _git(["clone", "--depth", "1", "--", url, str(source)], timeout)
        revision = _git(["-C", str(source), "rev-parse", "HEAD"], timeout).strip()
        submodules, warnings = _submodules(source, timeout)
        files = discover_files(source)
        # Keep the vendored source layout, not nested Git repositories.
        shutil.rmtree(source / ".git")
        for module in submodules:
            gitlink = source / module["path"] / ".git"
            if gitlink.is_file() or gitlink.is_symlink():
                gitlink.unlink()
        warnings += _symlink_warning(source)
        metadata = {
            "schema_version": "abb.agent-source.v1",
            "repository": url,
            "revision": revision,
            "downloaded_on": datetime.now(timezone.utc).date().isoformat(),
        }
        if submodules:
            metadata["submodules"] = submodules
        manifest = stage / "source-manifest.json"
        manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        unit = _reserve_directory(root, url, slug)
        try:
            source.rename(unit / "agent")
            manifest.rename(unit / manifest.name)
        except BaseException:
            shutil.rmtree(unit)
            raise
    return DownloadedAgent(unit, url, revision, files, tuple(warnings))


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
    owner_slug = f"{_slug(url.split('/')[3])}-{slug}"
    name_taken = False
    for path in root.iterdir():
        match = NUMBERED_UNIT.fullmatch(path.name)
        if not match or match[2].lower() not in {slug, owner_slug}:
            continue
        recorded = _recorded_repository(path)
        if recorded is None or recorded.casefold() == url.casefold():
            raise AgentDownloadError(f"Agent directory already exists: {path}")
        if match[2].lower() == owner_slug:
            raise AgentDownloadError(f"Agent directory name is used by {recorded}: {path}")
        name_taken = True
    return owner_slug if name_taken else slug


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
    missing = [item["path"] for item in submodules if not item["initialized"]]
    if missing:
        warnings.append("Submodules left empty, so the vendored source is incomplete: " + ", ".join(missing))
    return submodules, warnings


def _symlink_warning(source: Path) -> list[str]:
    links = []
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in [*directories, *files]:
            if Path(directory, name).is_symlink():
                links.append(Path(directory, name).relative_to(source).as_posix())
    if not links:
        return []
    shown = ", ".join(sorted(links)[:5]) + (f" and {len(links) - 5} more" if len(links) > 5 else "")
    return [f"{len(links)} symlink(s) kept; the Docker build context refuses symlinks, "
            f"so replace or remove them before building: {shown}"]


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

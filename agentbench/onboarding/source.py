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
    """
    url, slug = _github_source(repository)
    root = agents_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    _check_existing(root, slug)
    with tempfile.TemporaryDirectory(prefix=".agent-add-", dir=root) as temporary:
        stage = Path(temporary)
        source = stage / "agent"
        _git(["clone", "--depth", "1", "--", url, str(source)], timeout)
        revision = _git(["-C", str(source), "rev-parse", "HEAD"], timeout).strip()
        files = discover_files(source)
        # Keep the vendored source layout, not a nested Git repository.
        shutil.rmtree(source / ".git")
        metadata = {
            "schema_version": "abb.agent-source.v1",
            "repository": url,
            "revision": revision,
            "downloaded_on": datetime.now(timezone.utc).date().isoformat(),
        }
        manifest = stage / "source-manifest.json"
        manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        unit = _reserve_directory(root, slug)
        try:
            source.rename(unit / "agent")
            manifest.rename(unit / manifest.name)
        except BaseException:
            shutil.rmtree(unit)
            raise
    return DownloadedAgent(unit, url, revision, files)


def _github_source(repository: str) -> tuple[str, str]:
    try:
        value = urlsplit(repository)
    except ValueError as exc:
        raise AgentDownloadError("Invalid GitHub repository URL") from exc
    if (value.scheme != "https" or value.netloc.lower() != "github.com"
            or value.query or value.fragment):
        raise AgentDownloadError("Use an HTTPS GitHub repository URL: https://github.com/owner/repository")
    parts = value.path.strip("/").split("/")
    if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9-]+", parts[0]):
        raise AgentDownloadError("Expected a repository URL, not a GitHub file or branch URL")
    name = parts[1].removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
        raise AgentDownloadError("Invalid GitHub repository name")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise AgentDownloadError("Repository name must contain a letter or number")
    return f"https://github.com/{parts[0]}/{name}", slug


def _check_existing(root: Path, slug: str) -> None:
    for path in root.iterdir():
        match = NUMBERED_UNIT.fullmatch(path.name)
        if match and match[2].lower() == slug:
            raise AgentDownloadError(f"Agent directory already exists: {path}")


def _reserve_directory(root: Path, slug: str) -> Path:
    while True:
        _check_existing(root, slug)
        numbers = [int(match[1]) for path in root.iterdir()
                   if (match := NUMBERED_UNIT.fullmatch(path.name))]
        number = max(numbers, default=0) + 1
        path = root / f"{number:02d}-{slug}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path


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

"""Reuse a matching source checkout for explicit build/certify follow-up actions."""

import json
import os
from pathlib import Path

from .discovery import discover_files
from .source_status import checkout_warnings
from .source import AgentDownloadError, DownloadedAgent, NUMBERED_UNIT, _agent_source, download_agent


def download_or_reuse(repository: str, agents_directory: Path) -> DownloadedAgent:
    """Reuse only a manifest-matched source, preserving its local edits and revision."""
    selected = _agent_source(repository, require_local=False)
    identifier = selected.identifier
    root = agents_directory.resolve()
    matches = []
    for unit in sorted(root.iterdir()) if root.exists() else ():
        if not NUMBERED_UNIT.fullmatch(unit.name) or not unit.is_dir():
            continue
        manifest = unit / "source-manifest.json"
        if unit.is_symlink() or manifest.is_symlink() or not manifest.is_file():
            continue
        try:
            metadata = json.loads(manifest.read_text())
        except (ValueError, UnicodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        recorded = str(metadata.get("repository", ""))
        same = (os.path.normcase(recorded) == os.path.normcase(identifier)
                if selected.source_type == "local-directory"
                else recorded.casefold() == identifier.casefold())
        if not same:
            continue
        source = unit / "agent"
        if source.is_symlink() or not source.is_dir() or not isinstance(metadata.get("revision"), str):
            raise AgentDownloadError("Existing source manifest points to an invalid checkout")
        matches.append(DownloadedAgent(
            unit, identifier, metadata["revision"], discover_files(source),
            tuple(checkout_warnings(source, metadata.get("submodules", ()))),
            str(metadata.get("source_type", selected.source_type)),
        ))
    if len(matches) > 1:
        raise AgentDownloadError("Multiple downloaded units match this repository")
    return matches[0] if matches else download_agent(repository, agents_directory)

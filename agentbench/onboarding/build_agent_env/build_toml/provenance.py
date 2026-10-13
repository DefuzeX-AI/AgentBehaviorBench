"""Copy imported source facts from local records, never from model output."""

from datetime import date
import json
import re

from agentbench.runtime.agentcontainer.config import tomllib
from ..common.errors import BuildError
from ..openrouter_provider.context import safe_file


def source_metadata(source):
    """Read import metadata; older units may keep it in their existing manifest.

    Source identifier and revision must agree with the selected DownloadedAgent.
    Missing dates are omitted rather than replaced by today's date. No input file
    is modified.
    """
    data = {"repository": source.repository, "revision": source.revision}
    for name in ("source-manifest.json", "agent.toml"):
        path = safe_file(source.directory, name)
        if path is None:
            continue
        if path.stat().st_size > 262144:
            raise BuildError("Source metadata record is too large")
        recorded = (json.loads(path.read_text(encoding="utf-8")) if name.endswith(".json")
                    else tomllib.loads(path.read_text(encoding="utf-8")).get("source", {}))
        if not isinstance(recorded, dict):
            raise BuildError("Source metadata must be an object")
        for field in ("repository", "revision"):
            if field in recorded and recorded[field] != data[field]:
                raise BuildError(f"Source metadata {field} differs from the selected checkout")
        if "downloaded_on" in recorded:
            value = recorded["downloaded_on"]
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise BuildError("downloaded_on must use YYYY-MM-DD")
            data["downloaded_on"] = value
        break
    data["method"] = acquisition_method(source)
    return data


def acquisition_method(source):
    """Keep explicit policy; opt supported GitHub imports into pinned restoration."""
    path = safe_file(source.directory, "agent.toml")
    if path is not None:
        existing = tomllib.loads(path.read_text(encoding="utf-8")).get("source", {})
        if "method" in existing:
            from agentbench.runtime.source.config import source_spec
            source_spec({"source": existing, "runtime": {"type": "docker"}})
            return existing["method"]
    if source.source_type != "github" or not re.fullmatch(r"[0-9a-fA-F]{40}", source.revision):
        return "bundled"
    from agentbench.runtime.source.config import source_spec
    source_spec({"source": {"method": "git", "repository": source.repository,
                           "revision": source.revision}, "runtime": {"type": "docker"}})
    root = source.directory / "agent"
    if source.warnings or (root / ".gitmodules").exists():
        return "bundled"
    for path in root.rglob("*"):
        if path.is_symlink():
            return "bundled"
        if path.name == ".gitattributes" and path.is_file() and b"filter=lfs" in path.read_bytes():
            return "bundled"
    return "git"

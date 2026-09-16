"""Copy download facts from local records, never from model output."""

from datetime import date
import json

from agentbench.runtime.agentcontainer.config import tomllib
from ..common.errors import BuildError
from ..openrouter_provider.context import safe_file


def source_metadata(source):
    """Read download metadata; older units may keep it in their existing manifest.

    URL and revision must agree with the selected DownloadedAgent. Missing dates
    are omitted rather than replaced by today's date. No input file is modified.
    """
    data = {"repository": source.repository, "revision": source.revision}
    for name in ("source-manifest.json", "agent.toml"):
        path = safe_file(source.directory, name)
        if path is None:
            continue
        if path.stat().st_size > 262144:
            raise BuildError("Source metadata record is too large")
        recorded = (json.loads(path.read_text()) if name.endswith(".json")
                    else tomllib.loads(path.read_text()).get("source", {}))
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
    return data

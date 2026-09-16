"""Packaged defaults and optional user overrides for configuration generation."""

from dataclasses import dataclass, fields
from pathlib import Path

from agentbench.runtime.agentcontainer.config import tomllib
from ..common.errors import BuildError

ASSETS = Path(__file__).parent / "assets"


@dataclass(frozen=True)
class BuildSettings:
    model: str
    max_files: int
    max_file_bytes: int
    max_context_bytes: int
    max_response_bytes: int
    max_output_tokens: int
    timeout_seconds: int
    retries: int
    repair_attempts: int


def load_settings(path: Path | None = None) -> BuildSettings:
    """Read packaged settings, then merge an optional TOML [build] override."""
    values = tomllib.loads((ASSETS / "settings.toml").read_text())["build"]
    if path is not None:
        overrides = tomllib.loads(path.read_text(encoding="utf-8")).get("build")
        if not isinstance(overrides, dict):
            raise BuildError("Build settings need a [build] table")
        values.update(overrides)
    if set(values) != {item.name for item in fields(BuildSettings)}:
        raise BuildError("Unknown or missing build settings")
    for key, value in values.items():
        if key == "model":
            if not isinstance(value, str):
                raise BuildError("build.model must be a string")
        elif type(value) is not int or value < (0 if key in {"retries", "repair_attempts"} else 1):
            raise BuildError(f"Invalid build setting: {key}")
    return BuildSettings(**values)

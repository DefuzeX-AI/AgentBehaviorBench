"""Limit generated outputs to the integration unit, never upstream source."""

from pathlib import PurePosixPath

from .errors import BuildError

REQUIRED_FILES = frozenset({"agent.toml", "Dockerfile", ".dockerignore", "requirement.md"})
OPTIONAL_FILES = frozenset({"evaluation/input-schema.json"})


def file_path(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ".." in path.parts
            or path.as_posix() != name):
        raise BuildError("Invalid generated file path")
    binding = len(path.parts) == 2 and path.parts[0] == "bindings" and path.suffix == ".py"
    if name not in REQUIRED_FILES | OPTIONAL_FILES and not binding:
        raise BuildError(f"Output path is not an integration file: {name}")
    return name

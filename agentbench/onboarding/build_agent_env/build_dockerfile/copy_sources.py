"""Resolve generated COPY paths against the real outer Agent build context."""
import json
from pathlib import PurePosixPath
from .copy_instructions import instructions, from_stage
from ..common.errors import BuildError


def _relative(source):
    name = PurePosixPath(source)
    if name.is_absolute() or ".." in name.parts or "\\" in source:
        raise BuildError(f"Docker COPY source must stay inside the Agent unit: {source}")
    return name


def _exists(unit, source):
    name = _relative(source)
    if str(name) == "." or (name.parts and name.parts[0] == ".abb-runtime"):
        return True
    return any(path.resolve().is_relative_to(unit.resolve()) and not any(
        parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(unit)
    ) for path in unit.glob(str(name)))


def normalize_copy_sources(content, unit):
    """Qualify unambiguous upstream paths; preserve destinations and stage COPY.

    Only model-generated text goes through this renderer. Existing user files are
    never rewritten. Missing outer paths are prefixed only if the corresponding
    source path actually exists; unknown paths still fail normal validation.
    """
    result = []
    for block, copy in instructions(content):
        if copy is None or from_stage(copy[0]):
            result.append(block)
            continue
        flags, sources, destination = copy
        qualified = []
        for source in sources:
            name = _relative(source)
            candidate = "agent/" + str(name) + ("/" if source.endswith("/") else "")
            qualified.append(candidate if not _exists(unit, source) and _exists(unit, candidate) else source)
        if qualified == sources:
            result.append(block)
        else:
            prefix = "COPY " + (" ".join(flags) + " " if flags else "")
            result.append(prefix + json.dumps([*qualified, destination]) + "\n")
    return "".join(result)


def validate_copy_sources(content, unit):
    missing = []
    for _, copy in instructions(content):
        if copy is None or from_stage(copy[0]):
            continue
        for source in copy[1]:
            if not _exists(unit, source):
                candidate = "agent/" + str(_relative(source)) + ("/" if source.endswith("/") else "")
                hint = f" (actual build-context path: {candidate})" if _exists(unit, candidate) else ""
                missing.append(source + hint)
    if missing:
        raise BuildError("Docker COPY source does not exist: " + "; ".join(dict.fromkeys(missing)) +
                         ". Repository evidence paths are relative to agent/. Use COPY agent/ ./agent/ "
                         "for the complete source; generate the planned outer bindings before the Dockerfile.")

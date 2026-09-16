"""Parse shell/JSON Docker COPY syntax while retaining untouched instructions."""
import json
import re
import shlex
from ..common.errors import BuildError


def instructions(content):
    """Yield original logical blocks and optional (flags, sources, destination)."""
    block = ""
    for line in content.splitlines(keepends=True):
        block += line
        if line.rstrip().endswith("\\"):
            continue
        yield block, parse_copy(block.replace("\\\n", " ").strip())
        block = ""
    if block:
        yield block, parse_copy(block.strip())


def parse_copy(line):
    match = re.match(r"COPY\s+(.*)$", line, flags=re.I)
    if not match:
        return None
    value, flags = match[1], []
    while value.startswith("--"):
        flag, _, value = value.partition(" ")
        flags.append(flag)
        value = value.lstrip()
    try:
        parts = json.loads(value) if value.startswith("[") else shlex.split(value)
    except (ValueError, TypeError) as exc:
        raise BuildError(f"Invalid Docker COPY syntax: {exc}") from None
    if not isinstance(parts, list) or len(parts) < 2 or not all(isinstance(item, str) for item in parts):
        raise BuildError("Docker COPY requires source paths and a destination")
    return flags, parts[:-1], parts[-1]


def from_stage(flags):
    return any(flag.startswith("--from=") for flag in flags)

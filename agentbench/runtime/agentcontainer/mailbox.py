"""File mailbox between a host chat loop and its in-container chat worker.

The host owns the read-only input mount and publishes one turn file per user
message, then an end marker. The worker owns the output mount and answers each
turn in its own ``steps/NNNN/`` directory, the step layout SDK attempts use, so
the trajectory and viewer readers need no chat-specific branch.
"""
import json
import os
import tempfile
from pathlib import Path

SCHEMA = "abb.chat.turn.v1"
WORKER_MODULE = "agentbench.runtime.agentcontainer.chat"
ONESHOT_MODULE = "agentbench.runtime.agentcontainer.worker"


def turn_name(number):
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 9999:
        raise ValueError("Chat turn numbers range from 1 to 9999")
    return f"{number:04d}"


def turn_path(mailbox, number):
    return Path(mailbox) / "turns" / f"{turn_name(number)}.json"


def end_path(mailbox):
    return Path(mailbox) / "turns" / "end.json"


def step_directory(output, number):
    return Path(output) / "steps" / turn_name(number)


def turn(number, value):
    return {"schema": SCHEMA, "turn": number, "input": value}


def read_turn(path, number):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("turn") != number or "input" not in value:
        raise ValueError(f"Invalid chat turn file: {path}")
    return value


def post(path, value):
    """Publish a complete file the container user can read, in one rename.

    The worker polls for exact names, so it never sees the hidden temporary.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

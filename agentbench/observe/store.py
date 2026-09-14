"""Append-only, run-scoped trace storage shared by host and worker."""
from __future__ import annotations

import json
import os
import threading
import tempfile
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path


def json_value(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump())
    return {"type": type(value).__name__, "value": str(value)}


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if any(x in k.lower() for x in
                ("api_key", "authorization", "secret", "password", "access_token"))
                else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def atomic_json(path: Path, value):
    # Independent writers must never share the same intermediate pathname.
    stream = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = Path(stream.name)
    try:
        with stream:
            json.dump(json_value(value), stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class TraceStore:
    def __init__(self, path: Path, run_id: str, *, source="runtime", context=None,
                 environ=None):
        self.path, self.run_id, self.source = path, run_id, source
        # Authoritative invocation identity, shared by every event in this store.
        self.context = dict(context or {})
        self._lock = threading.Lock()
        environment = os.environ if environ is None else environ
        self._secrets = tuple(v for k, v in environment.items()
                              if any(x in k.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD")))

    def record(self, event: str, **data):
        row = {"schema": "abb.observe.event.v1", "run_id": self.run_id,
               "source": self.source, "event": event,
               "timestamp": datetime.now(timezone.utc).isoformat(),
               "data": redact(json_value({**data, **self.context}), self._secrets)}
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()

    def emit(self, event):
        self.record(event.event, **dict(event.data))


def summarize(directory: Path):
    counts = {}
    for path in sorted(directory.rglob("*.jsonl")):
        if path.is_symlink():
            continue
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                counts["incomplete_lines"] = counts.get("incomplete_lines", 0) + 1
                continue
            key = row["source"] + ":" + row["event"]
            counts[key] = counts.get(key, 0) + 1
            if row["event"] == "tool_outcome" and row["data"].get("status") != "succeeded":
                warning = row["source"] + ":tool_incomplete"
                counts[warning] = counts.get(warning, 0) + 1
    return counts

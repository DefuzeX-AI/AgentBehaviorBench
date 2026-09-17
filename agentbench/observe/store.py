"""Append-only, run-scoped trace storage shared by host and worker."""
from __future__ import annotations

import json
import os
import re
import threading
import tempfile
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from functools import lru_cache
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


REDACTED = "[REDACTED]"
# At or above this length a value is replaced wherever it appears; shorter
# harvested values only as a whole token, so they cannot rewrite identifiers.
_SUBSTRING_SECRET_LENGTH = 16
# A field is a credential when its last word says so ("access_token",
# "credentials", "x-api-key"), not when a word merely occurs in it: "max_tokens",
# "api_key_source" and "secret_env_keys" carry counts, provenance and names.
_SECRET_FIELD_WORDS = frozenset({"token", "secret", "password", "passwd", "passphrase", "credential",
                                 "credentials", "authorization", "bearer", "apikey", "cookie"})
_KEY_QUALIFIERS = frozenset({"api", "private", "access", "secret", "signing", "encryption", "auth", "session",
                             "client"})


def environment_secrets(environ=None) -> tuple[str, ...]:
    """Harvest actual credential fields, without guessing secret strength.

    This is the single harvesting rule. Selecting on the variable name alone
    swept in settings such as GOG_KEYRING_BACKEND=file, and the value "file"
    then rewrote every artifact: a traceback's ``is_file()`` became
    ``is_[REDACTED]()`` in the one diagnostic that explained a failure.
    """
    values = os.environ if environ is None else environ
    secrets = []
    for key, value in values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if value and is_secret_field(key):
            secrets.append(value)
    return tuple(secrets)


def is_secret_field(key) -> bool:
    """Whether a mapping key names a credential, after normalizing its spelling."""
    words = [word for word in re.split(r"[^a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).lower())
             if word]
    if words and words[-1] in {"value", "val", "hash"}:
        words = words[:-1]  # "secret_value", "api_key_value": the credential itself
    if not words:
        return False
    if words[-1] in _SECRET_FIELD_WORDS:
        return True
    return words[-1] == "key" and len(words) > 1 and words[-2] in _KEY_QUALIFIERS


@lru_cache(maxsize=64)
def _secret_patterns(secrets: tuple[str, ...]):
    long_values = sorted({secret for secret in secrets if len(secret) >= _SUBSTRING_SECRET_LENGTH}, key=len,
                         reverse=True)
    short_values = sorted({secret for secret in secrets if 0 < len(secret) < _SUBSTRING_SECRET_LENGTH}, key=len,
                          reverse=True)
    long_pattern = re.compile("|".join(map(re.escape, long_values))) if long_values else None
    short_pattern = (re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, short_values)) + r")(?![A-Za-z0-9_])")
                     if short_values else None)
    return long_pattern, short_pattern


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {k: REDACTED if is_secret_field(k) else redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str) and secrets:
        long_pattern, short_pattern = _secret_patterns(tuple(secret for secret in secrets if secret))
        if long_pattern is not None:
            value = long_pattern.sub(REDACTED, value)
        if short_pattern is not None:
            value = short_pattern.sub(REDACTED, value)
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
        self._secrets = environment_secrets(environ)

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

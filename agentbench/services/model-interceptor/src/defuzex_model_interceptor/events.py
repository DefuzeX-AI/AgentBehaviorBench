"""Trace event formatting and unconditional secret redaction."""

from __future__ import annotations

import json
from collections.abc import Mapping


TRACE_PREFIX = "DEFUZEX_TRACE "
SECRET_KEYS = {"authorization", "api_key", "apikey", "token", "secret", "password"}


def emit(event: str, **data: object) -> None:
    print(
        TRACE_PREFIX + json.dumps({"event": event, **data}, ensure_ascii=False),
        flush=True,
    )


def redact(value: object, secrets: tuple[str, ...]) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _secret_key(str(key)) else redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            if secret:
                redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value


def _secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SECRET_KEYS or any(
        normalized.endswith(f"_{suffix}") for suffix in SECRET_KEYS
    )

"""Small conversion helpers for Java API compatibility.

The original controllers receive and return camelCase JSON. Internally the
Python code uses snake_case database columns, so this module normalizes request
payload keys before service code touches them.
"""

import re
from datetime import datetime
from typing import Any


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def to_snake(name: str) -> str:
    """Convert a Java-style camelCase field name into Python snake_case."""

    return _CAMEL_RE.sub("_", name).lower()


def parse_datetime(value: Any) -> Any:
    """Parse ISO datetime strings but leave non-datetime values unchanged."""

    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize incoming JSON to names accepted by SQLAlchemy models."""

    return {to_snake(key): parse_datetime(value) for key, value in payload.items()}


def update_present_fields(target: Any, payload: dict[str, Any], fields: set[str]) -> None:
    """Update only fields explicitly provided by the caller."""

    for key, value in payload.items():
        if key in fields and value is not None:
            setattr(target, key, value)


def require_text(value: str | None, message: str) -> None:
    """Raise the same kind of validation error the Java service raised."""

    if value is None or not str(value).strip():
        raise ValueError(message)

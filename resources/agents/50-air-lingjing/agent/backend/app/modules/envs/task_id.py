"""Beijing-timezone task id allocation.

Every closed-loop episode is identified by a deterministic Beijing-time
timestamp so that realtime data rows written to SQLite can be filtered per
task without relying on opaque UUIDs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """Return the current time in Asia/Shanghai (UTC+8)."""

    return datetime.now(BEIJING_TZ)


def make_task_id(prefix: str = "task") -> str:
    """Generate a task id like ``task_20260520_141532_123`` (millisecond)."""

    now = beijing_now()
    millis = now.microsecond // 1000
    return f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}_{millis:03d}"


def beijing_iso(now: datetime | None = None) -> str:
    """ISO-8601 string in Beijing time."""

    return (now or beijing_now()).isoformat()

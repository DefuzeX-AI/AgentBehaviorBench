from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from models.common import SessionStatus


@dataclass
class SessionRecord:
    """In-memory session snapshot for MVP API endpoints."""

    session_id: str
    request_id: str
    status: SessionStatus
    data: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemorySessionStore:
    """Thread-safe session state store used by API layer before persistence is added."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def upsert(self, record: SessionRecord) -> None:
        with self._lock:
            record.updated_at = datetime.now(UTC)
            self._sessions[record.session_id] = record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def update(
        self,
        session_id: str,
        *,
        status: SessionStatus | None = None,
        data: dict[str, Any] | None = None,
    ) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if status is not None:
                record.status = status
            if data is not None:
                record.data = data
            record.updated_at = datetime.now(UTC)
            return record

    def cancel(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.status = SessionStatus.cancelled
            record.data["current_step"] = "cancelled"
            record.events.append(
                {
                    "type": "session_cancelled",
                    "payload": {"current_step": "cancelled"},
                }
            )
            record.updated_at = datetime.now(UTC)
            return record

    def append_event(self, session_id: str, event: dict[str, Any]) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            record.events.append(event)
            record.updated_at = datetime.now(UTC)
            return record

    def get_events(self, session_id: str, after_index: int = 0) -> list[dict[str, Any]] | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if after_index < 0:
                after_index = 0
            return record.events[after_index:]

    def cleanup_expired(self, ttl_days: int) -> int:
        """Remove expired sessions by updated_at TTL; returns removed count."""
        with self._lock:
            now = datetime.now(UTC)
            ttl = timedelta(days=ttl_days)
            expired_ids = [sid for sid, rec in self._sessions.items() if now - rec.updated_at > ttl]
            for sid in expired_ids:
                del self._sessions[sid]
            return len(expired_ids)

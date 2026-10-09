from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass
class UploadedFileRecord:
    """In-memory file metadata with on-disk payload path."""

    file_id: str
    filename: str
    content_type: str
    path: str
    size_bytes: int
    purpose: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryFileStore:
    """
    Thread-safe uploaded-file registry.
    File bytes are persisted to local temp directory; metadata stays in memory.
    """

    SUPPORTED_SUFFIXES = {".pdf", ".doc", ".docx", ".txt"}

    def __init__(self, *, root_dir: str | Path) -> None:
        self._lock = Lock()
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, UploadedFileRecord] = {}

    def save_file(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        purpose: str | None = None,
    ) -> UploadedFileRecord:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported file type: {suffix}")
        if not data:
            raise ValueError("Uploaded file is empty.")

        file_id = str(uuid4())
        target_name = f"{file_id}{suffix}"
        target_path = (self._root / target_name).resolve()
        target_path.write_bytes(data)
        record = UploadedFileRecord(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            path=str(target_path),
            size_bytes=len(data),
            purpose=purpose,
        )
        with self._lock:
            self._files[file_id] = record
        return record

    def get(self, file_id: str) -> UploadedFileRecord | None:
        with self._lock:
            return self._files.get(file_id)

    def delete(self, file_id: str) -> bool:
        """Delete one uploaded file record and unlink payload from disk."""
        with self._lock:
            record = self._files.pop(file_id, None)
        if record is None:
            return False
        try:
            Path(record.path).unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def cleanup_expired(self, ttl_hours: int) -> int:
        """Remove expired uploads and unlink files on disk."""
        with self._lock:
            now = datetime.now(UTC)
            ttl = timedelta(hours=ttl_hours)
            expired_ids = [fid for fid, rec in self._files.items() if now - rec.updated_at > ttl]
            removed = 0
            for file_id in expired_ids:
                rec = self._files.pop(file_id, None)
                if rec is None:
                    continue
                try:
                    Path(rec.path).unlink(missing_ok=True)
                except OSError:
                    pass
                removed += 1
            return removed

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"file_count": len(self._files)}

"""Thread-safe resource names and ownership, including interrupted creates."""

from __future__ import annotations

import threading
from collections.abc import Mapping


class ResourceRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._resources: dict[tuple[str, str], dict[str, object]] = {}

    def plan(self, kind: str, name: str, identity: Mapping[str, object]) -> None:
        with self._lock:
            key = (kind, name)
            if key in self._resources:
                raise ValueError(f"Resource already belongs to this Suite: {name}")
            self._resources[key] = dict(kind=kind, name=name, identity=dict(identity), status="planned")

    def created(self, kind: str, name: str, resource_id: str | None = None) -> None:
        with self._lock:
            self._resources[kind, name].update(status="created", resource_id=resource_id)

    def removed(self, kind: str, name: str) -> None:
        with self._lock:
            self._resources[kind, name].update(status="removed")

    def failed(self, kind: str, name: str, error: str) -> None:
        with self._lock:
            self._resources[kind, name].update(status="cleanup_failed", cleanup_error=error)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        with self._lock:
            return tuple({**value, "identity": dict(value["identity"])} for value in self._resources.values())

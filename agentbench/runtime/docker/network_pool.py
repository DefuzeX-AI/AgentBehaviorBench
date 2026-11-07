"""Suite-scoped reuse of Case networks to avoid host network churn (#421).

Creating and deleting a bridge per Case adds and removes a host interface and
gateway address each time, which desktop software treats as a network change
(Chrome aborts requests with ERR_NETWORK_CHANGED). The pool keeps each network
exclusive to one Case at a time and removes them only when the Suite closes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from uuid import uuid4

Remover = Callable[[str], None]


class NetworkPool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token = uuid4().hex[:12]
        self._count = 0
        self._free: dict[bool, list[str]] = {False: [], True: []}
        self._owned: dict[str, Remover] = {}

    def take(self, internal: bool) -> str | None:
        """Return a free network of the requested kind, exclusive to the caller."""
        with self._lock:
            free = self._free[internal]
            return free.pop() if free else None

    def new_name(self, internal: bool) -> str:
        with self._lock:
            self._count += 1
            index = self._count
        return f"defuzex-pool-{self._token}-{index}-{'internal' if internal else 'egress'}"

    def adopt(self, name: str, remove: Remover) -> None:
        """Record a created pool network and how to remove it at Suite close."""
        with self._lock:
            self._owned[name] = remove

    def release(self, name: str, internal: bool) -> None:
        with self._lock:
            if name in self._owned and name not in self._free[internal]:
                self._free[internal].append(name)

    def discard(self, name: str) -> None:
        with self._lock:
            self._owned.pop(name, None)
            for free in self._free.values():
                if name in free:
                    free.remove(name)

    def close(self) -> list[str]:
        """Remove every pool network; return error messages instead of raising early."""
        with self._lock:
            owned, self._owned = self._owned, {}
            self._free = {False: [], True: []}
        errors: list[str] = []
        for name, remove in owned.items():
            try:
                remove(name)
            except Exception as exc:
                errors.append(str(exc))
        return errors

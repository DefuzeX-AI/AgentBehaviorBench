"""Vendor-independent cancellation and finite runtime budgets."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


class RunCancelled(RuntimeError):
    """The caller requested cooperative cancellation of this run."""


class RuntimeInfrastructureError(RuntimeError):
    """A shared runtime failure requires the Suite to stop dispatching work."""


class DockerCleanupError(RuntimeInfrastructureError):
    """Resources could not be confirmed removed within the cleanup budget."""


class RunControl:
    """A shareable cancellation signal; a new Suite must create a new control."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._forced = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def forced(self) -> bool:
        return self._forced.is_set()

    def cancel(self) -> None:
        self._cancelled.set()

    def force_cancel(self) -> None:
        self._forced.set()
        self.cancel()

    def check(self) -> None:
        if self.cancelled:
            raise RunCancelled("Agent test cancelled")

    def wait(self, seconds: float) -> bool:
        """Wait at most seconds; return True when cancellation was requested."""
        return self._cancelled.wait(seconds)


@dataclass(frozen=True, slots=True)
class Deadline:
    expires_at: float

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Runtime timeout must be finite and positive")
        return cls(time.monotonic() + seconds)

    def remaining(self) -> float:
        return max(0.0, self.expires_at - time.monotonic())

    def check(self) -> None:
        if not self.remaining():
            raise TimeoutError("Runtime preparation exceeded its time budget")


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    command_seconds: float = 60
    preparation_seconds: float = 1800
    build_seconds: float = 1800
    startup_seconds: float = 45
    execution_seconds: float = 2400
    cleanup_seconds: float = 45

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

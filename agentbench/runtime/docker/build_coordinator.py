"""One Suite's image single-flight cache and internal serial build slot."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future

from agentbench.runtime.contracts.execution import Deadline, RunControl, RuntimeInfrastructureError


class BuildCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slot = threading.BoundedSemaphore(1)
        self._records: dict[object, Future[str]] = {}
        self._failure: RuntimeInfrastructureError | None = None

    def resolve(
        self, key: object, *, inspect_cached: Callable[[], str | None],
        build_once: Callable[[], str], control: RunControl | None = None,
        deadline: Deadline | None = None,
    ) -> str:
        self._check(control, deadline)
        with self._lock:
            if self._failure is not None:
                raise self._failure
            future = self._records.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._records[key] = future
        assert future is not None
        if not owner:
            while not future.done():
                self._check(control, deadline)
                if control is not None:
                    control.wait(0.05)
                else:
                    threading.Event().wait(0.05)
            self._check(control, deadline)
            return future.result()
        try:
            cached = inspect_cached()
            if cached is not None:
                future.set_result(cached)
                return cached
            while not self._slot.acquire(timeout=0.05):
                self._check(control, deadline)
            try:
                self._check(control, deadline)
                with self._lock:
                    if self._failure is not None:
                        raise self._failure
                # Another process may have populated Docker's cache meanwhile.
                result = inspect_cached() or build_once()
            finally:
                self._slot.release()
            future.set_result(result)
            return result
        except BaseException as exc:
            if isinstance(exc, RuntimeInfrastructureError):
                with self._lock:
                    self._failure = exc
            future.set_exception(exc)
            raise

    @staticmethod
    def _check(control: RunControl | None, deadline: Deadline | None) -> None:
        if control is not None:
            control.check()
        if deadline is not None:
            deadline.check()

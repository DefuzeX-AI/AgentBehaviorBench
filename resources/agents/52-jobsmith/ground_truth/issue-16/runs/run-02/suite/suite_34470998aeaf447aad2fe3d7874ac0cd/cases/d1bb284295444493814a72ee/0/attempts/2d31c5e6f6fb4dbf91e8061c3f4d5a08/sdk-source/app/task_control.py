"""Cooperative cancellation for user-triggered long-running tasks."""

from __future__ import annotations

import contextlib
import contextvars
import threading
import uuid
from collections.abc import Iterator


class TaskCancelled(RuntimeError):
    """Raised when the current user task has been cancelled."""


class TaskToken:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def check(self) -> None:
        if self.is_cancelled():
            raise TaskCancelled("已停止任務")


_LOCK = threading.Lock()
_TASKS: dict[str, TaskToken] = {}
_CURRENT: contextvars.ContextVar[TaskToken | None] = contextvars.ContextVar(
    "current_task_token",
    default=None,
)


def create_task(task_id: str | None = None) -> TaskToken:
    tid = (task_id or "").strip() or uuid.uuid4().hex
    with _LOCK:
        token = _TASKS.get(tid)
        if token is None:
            token = TaskToken(tid)
            _TASKS[tid] = token
        return token


def get_task(task_id: str) -> TaskToken | None:
    with _LOCK:
        return _TASKS.get(task_id)


def request_stop(task_id: str) -> bool:
    token = get_task(task_id)
    if token is None:
        return False
    token.cancel()
    return True


def finish_task(task_id: str) -> None:
    with _LOCK:
        _TASKS.pop(task_id, None)


def current_task() -> TaskToken | None:
    return _CURRENT.get()


def check_cancelled() -> None:
    token = current_task()
    if token is not None:
        token.check()


def is_cancelled() -> bool:
    token = current_task()
    return bool(token and token.is_cancelled())


@contextlib.contextmanager
def task_context(token: TaskToken | None) -> Iterator[None]:
    marker = _CURRENT.set(token)
    try:
        yield
    finally:
        _CURRENT.reset(marker)

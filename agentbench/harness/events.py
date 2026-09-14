"""Bounded worker-to-coordinator callbacks; large trace bodies stay on disk."""

from collections import OrderedDict
from collections.abc import Mapping
from copy import copy, deepcopy
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from queue import Empty, Full, Queue
import threading
from uuid import uuid4


class EventDeliveryError(RuntimeError):
    pass


def _snapshot(value, memo=None):
    """Detach callback data, including SDK dataclasses with immutable mappings.

    ``deepcopy`` alone cannot copy MappingProxyType. Preserve dataclass types
    for the public callbacks, while detaching their nested containers.
    """
    memo = {} if memo is None else memo
    if id(value) in memo:
        return memo[id(value)]
    if isinstance(value, Mapping):
        result = {}
        memo[id(value)] = result
        result.update((_snapshot(key, memo), _snapshot(item, memo))
                      for key, item in value.items())
        return result
    if is_dataclass(value) and not isinstance(value, type):
        result = copy(value)
        memo[id(value)] = result
        for field in fields(value):
            object.__setattr__(result, field.name, _snapshot(getattr(value, field.name), memo))
        return result
    if isinstance(value, list):
        result = []
        memo[id(value)] = result
        result.extend(_snapshot(item, memo) for item in value)
        return result
    if isinstance(value, (tuple, set, frozenset)):
        result = type(value)(_snapshot(item, memo) for item in value)
        memo[id(value)] = result
        return result
    return deepcopy(value, memo)


class EventBus:
    def __init__(self, *, on_event=None, on_tick=None, capacity=1024):
        self.on_event = on_event
        self.on_tick = on_tick
        self._owner = threading.get_ident()
        self._queue = Queue(maxsize=capacity)
        self._previews = OrderedDict()
        self._lock = threading.Lock()
        self._error = None
        self._sequence = 0
        self.dropped_previews = 0

    def publish(self, event, callback=None, args=()):
        # Freeze data before the runner advances its Case/SDK state.
        value = (_snapshot(event), callback, _snapshot(args))
        if threading.get_ident() == self._owner:
            self._deliver(value)
            return
        while True:
            if self._error is not None:
                raise EventDeliveryError("Suite event consumer failed") from self._error
            try:
                self._queue.put(value, timeout=0.1)
                return
            except Full:
                continue

    def preview(self, key, callback, value):
        if self._error is not None or callback is None:
            return
        with self._lock:
            if key in self._previews:
                self.dropped_previews += 1
                del self._previews[key]
            self._previews[key] = (callback, value)
            if len(self._previews) > 256:
                self._previews.popitem(last=False)
                self.dropped_previews += 1

    def drain(self, *, limit=100, discard=False):
        for _ in range(limit):
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if not discard:
                self._deliver(item)
        with self._lock:
            previews = list(self._previews.values())
            self._previews.clear()
        if not discard:
            for callback, event in previews:
                try:
                    callback(event)
                except BaseException as exc:
                    self.fail(exc)
                    raise
            if self.on_tick is not None:
                try:
                    self.on_tick()
                except BaseException as exc:
                    self.fail(exc)
                    raise

    def drain_published(self, *, discard=False):
        # Called after a Future is done: all of that job's events are already
        # in this FIFO. Capture a bounded prefix, ignoring newer producers.
        self.drain(limit=self._queue.qsize(), discard=discard)

    def fail(self, error):
        self._error = error

    def _deliver(self, value):
        event, callback, args = value
        self._sequence += 1
        event = {
            "event_id": uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
            "sequence": self._sequence,
        }
        try:
            if self.on_event is not None:
                self.on_event(event)
            if callback is not None:
                callback(*args)
        except BaseException as exc:
            self.fail(exc)
            raise


class QueuedTraceSink:
    def __init__(self, bus, target, identity):
        self.bus, self.target, self.identity = bus, target, dict(identity)

    def emit(self, event):
        from agentbench.runtime.interception import TraceEvent

        def bounded(value, depth=0):
            if isinstance(value, str):
                return value[:512]
            if depth > 5:
                return "[preview]"
            if isinstance(value, dict):
                return {str(k)[:80]: bounded(v, depth + 1)
                        for k, v in list(value.items())[:10]}
            if isinstance(value, (list, tuple)):
                return [bounded(v, depth + 1) for v in value[-4:]]
            return value if value is None or isinstance(value, (bool, int, float)) else "[preview]"

        data = bounded(dict(event.data))
        # Rich trace payloads may put the trusted run/Case fields after the
        # first ten keys. Keep the routing and useful preview fields explicitly
        # so delayed calls from separate Cases never coalesce under None IDs.
        for key in ("artifact_run_id", "artifact_directory", "case_index", "case_id",
                    "sdk_run_id", "phase", "call_id", "provider", "payload", "status",
                    "error", "purpose", "method", "host", "path", "latency_ms"):
            if key in event.data:
                data[key] = bounded(event.data[key])
        data.update(self.identity)
        # Request/response can coalesce independently; evidence was persisted
        # upstream before this UI-only path is called.
        key = (data.get("job_id"), data.get("artifact_run_id"),
               data.get("call_id"), event.event)
        callback = getattr(self.target, "emit", None)
        self.bus.preview(key, callback, TraceEvent(event.event, data))

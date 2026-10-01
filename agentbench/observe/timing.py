"""Persistent operation timings, independent of viewers and framework evidence.

Each process writes its own journal. Durations use a local monotonic clock;
wall-clock anchors are only for arranging different processes on a timeline.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import logging
from pathlib import Path
import threading
import time
from uuid import uuid4

from .store import TraceStore

_recorder = ContextVar('abb_timing_recorder', default=None)
_parent = ContextVar('abb_timing_parent', default=None)


class Operation:
    def __init__(self, recorder, name, kind, attributes):
        self.recorder = recorder
        self.started = time.perf_counter_ns()
        self.status = 'succeeded'
        self.data = dict(id=uuid4().hex, parent_id=_parent.get(), name=name, kind=kind,
                         start_ms=time.time_ns() / 1e6, clock_id=recorder.clock_id,
                         attributes=attributes, source=recorder.source)

    def snapshot(self, status='running'):
        duration = max(0, (time.perf_counter_ns() - self.started) / 1e6)
        return {**self.data, 'duration_ms': duration, 'end_ms': self.data['start_ms'] + duration,
                'status': status}


class TimingRecorder:
    def __init__(self, path, *, source, identity=None, heartbeat_seconds=2):
        self.source = source
        self.clock_id = uuid4().hex
        self.store = TraceStore(Path(path), self.clock_id, source='timing', context=identity)
        self.active = {}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.heartbeat_seconds = heartbeat_seconds
        self.failed = False

    def write(self, operation, status='running'):
        try:
            self.store.record('operation', **operation.snapshot(status))
        except OSError:
            if not self.failed:
                logging.getLogger(__name__).warning('Timing journal is unavailable; timings may be incomplete')
            self.failed = True

    def heartbeat(self):
        while not self.stop.wait(self.heartbeat_seconds):
            with self.lock:
                for operation in self.active.values():
                    self.write(operation)


@contextmanager
def timing_session(path, *, source, name, identity=None):
    recorder = TimingRecorder(path, source=source, identity=identity)
    token = _recorder.set(recorder)
    parent_token = _parent.set(None)
    thread = threading.Thread(target=recorder.heartbeat, name='abb-timing', daemon=True)
    thread.start()
    try:
        with span(name, kind='total') as operation:
            yield operation
    finally:
        recorder.stop.set()
        thread.join(timeout=3)
        _parent.reset(parent_token)
        _recorder.reset(token)


@contextmanager
def span(name, *, kind='runtime', **attributes):
    recorder = _recorder.get()
    if recorder is None:
        yield None
        return
    operation = Operation(recorder, name, kind, attributes)
    token = _parent.set(operation.data['id'])
    with recorder.lock:
        recorder.active[operation.data['id']] = operation
        recorder.write(operation)
    try:
        yield operation
    except BaseException as exc:
        operation.status = ('cancelled' if type(exc).__name__ in {'RunCancelled', 'CancelledError', 'KeyboardInterrupt'}
                            else 'failed')
        raise
    finally:
        with recorder.lock:
            recorder.write(operation, operation.status)
            recorder.active.pop(operation.data['id'], None)
        _parent.reset(token)


def timed(name, *, kind='runtime'):
    """Instrument ordinary sync/async functions; generators need explicit spans."""
    def decorate(function):
        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with span(name, kind=kind):
                    return await function(*args, **kwargs)
            return asynchronous
        @wraps(function)
        def synchronous(*args, **kwargs):
            with span(name, kind=kind):
                return function(*args, **kwargs)
        return synchronous
    return decorate

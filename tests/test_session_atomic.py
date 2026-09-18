import os

import pytest

from agentbench.harness.session import atomic


def _sharing_violation():
    error = PermissionError(13, "The process cannot access the file")
    error.winerror = 5
    return error


def test_atomic_bytes_retries_a_temporary_windows_sharing_violation(tmp_path, monkeypatch):
    target = tmp_path / "events.json"
    target.write_bytes(b"old")
    real_replace = os.replace
    attempts = []
    delays = []

    def temporarily_locked(source, destination):
        attempts.append((source, destination))
        if len(attempts) < 3:
            raise _sharing_violation()
        real_replace(source, destination)

    monkeypatch.setattr(atomic, "_WINDOWS", True, raising=False)
    monkeypatch.setattr(atomic.os, "replace", temporarily_locked)
    monkeypatch.setattr(atomic.time, "sleep", delays.append, raising=False)

    atomic.atomic_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert len(attempts) == 3
    assert delays == [0.01, 0.02]


def test_atomic_bytes_stops_retrying_a_persistent_windows_denial(tmp_path, monkeypatch):
    target = tmp_path / "events.json"
    target.write_bytes(b"old")
    attempts = []
    delays = []

    def persistently_locked(source, destination):
        attempts.append((source, destination))
        raise _sharing_violation()

    monkeypatch.setattr(atomic, "_WINDOWS", True, raising=False)
    monkeypatch.setattr(atomic.os, "replace", persistently_locked)
    monkeypatch.setattr(atomic.time, "sleep", delays.append, raising=False)

    with pytest.raises(PermissionError) as raised:
        atomic.atomic_bytes(target, b"new")

    assert raised.value.winerror == 5
    assert target.read_bytes() == b"old"
    assert len(attempts) == 8
    assert delays == [0.01, 0.02, 0.04, 0.08, 0.16, 0.2, 0.2]


def test_atomic_bytes_does_not_retry_other_permission_errors(tmp_path, monkeypatch):
    target = tmp_path / "events.json"
    attempts = []

    def denied(source, destination):
        attempts.append((source, destination))
        error = PermissionError(13, "Permission denied")
        error.winerror = 87
        raise error

    monkeypatch.setattr(atomic, "_WINDOWS", True, raising=False)
    monkeypatch.setattr(atomic.os, "replace", denied)
    monkeypatch.setattr(atomic.time, "sleep", lambda delay: pytest.fail("unexpected retry"), raising=False)

    with pytest.raises(PermissionError):
        atomic.atomic_bytes(target, b"new")

    assert len(attempts) == 1

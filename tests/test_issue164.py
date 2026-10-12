"""History publication waits; Suite ownership still excludes other writers."""
import subprocess
import sys
import time

import pytest

from agentbench.harness.session.locking import SuiteLock, SuiteLockedError
from agentbench.harness.session.references import history_guard


def child(program, root):
    return subprocess.Popen([sys.executable, '-u', '-c', program, str(root)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def finish(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)


def test_history_contender_waits_until_another_process_releases(tmp_path):
    program = (
        'import sys\n'
        'from agentbench.harness.session.references import history_guard\n'
        'print("ready", flush=True)\n'
        'with history_guard(sys.argv[1]): print("acquired", flush=True)\n')
    process = None
    try:
        with history_guard(tmp_path):
            process = child(program, tmp_path)
            assert process.stdout.readline().strip() == 'ready'
            time.sleep(0.2)
            assert process.poll() is None, 'Contender must wait instead of exiting'
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, err
        assert out.strip() == 'acquired'
    finally:
        if process is not None:
            finish(process)


def test_history_timeout_is_bounded_and_names_lock(tmp_path):
    started = time.monotonic()
    with history_guard(tmp_path):
        started = time.monotonic()
        with pytest.raises(RuntimeError, match='Timed out after 0.2s') as error:
            with history_guard(tmp_path, timeout=0.2):
                pytest.fail('Two publishers entered the critical section')
        assert 0.15 <= time.monotonic() - started < 3
        assert str(tmp_path / 'cache/history-guard/.writer.lock') in str(error.value)
    with history_guard(tmp_path, timeout=0):
        pass


def test_crashed_holder_does_not_leave_stale_history_lock(tmp_path):
    program = (
        'import os, sys\n'
        'from agentbench.harness.session.references import history_guard\n'
        'with history_guard(sys.argv[1]):\n'
        ' print("acquired", flush=True)\n'
        ' sys.stdin.readline()\n'
        ' os._exit(7)\n')
    process = child(program, tmp_path)
    try:
        assert process.stdout.readline().strip() == 'acquired'
        with pytest.raises(RuntimeError, match='Timed out'):
            with history_guard(tmp_path, timeout=0):
                pytest.fail('Holder must retain exclusive ownership')
        process.communicate(input='exit\n', timeout=10)
        assert process.returncode == 7
        with history_guard(tmp_path, timeout=0):
            pass
    finally:
        finish(process)


def test_exception_releases_history_lock(tmp_path):
    with pytest.raises(ValueError, match='publication failed'):
        with history_guard(tmp_path):
            raise ValueError('publication failed')
    with history_guard(tmp_path, timeout=0):
        pass


def test_suite_lock_rejects_second_owner_and_acquire_is_idempotent(tmp_path):
    owner, contender = SuiteLock(tmp_path), SuiteLock(tmp_path)
    try:
        owner.acquire()
        owner.acquire()
        owner.check()
        with pytest.raises(SuiteLockedError):
            contender.acquire()
        owner.close()
        with pytest.raises(RuntimeError, match='owning process'):
            owner.check()
        contender.acquire()
        contender.check()
    finally:
        owner.close()
        contender.close()


def test_io_failure_is_not_reported_as_contention(tmp_path):
    root = tmp_path / 'not-a-directory'
    root.write_text('file')
    with pytest.raises(OSError):
        SuiteLock(root).acquire(timeout=0.1)

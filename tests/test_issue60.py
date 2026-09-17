"""Issue #60: CLI progress reaches a redirected stdout when it is printed, not at exit."""
import os
import selectors
import subprocess
import sys
import time

CHILD = """
import time
from agentbench.cli.main import _line_buffer_console
{configure}
print('Running: [1/1] progress line', flush=False)
time.sleep(60)
"""


def _first_line_within(configure, seconds=10.0):
    environment = {key: value for key, value in os.environ.items() if key != 'PYTHONUNBUFFERED'}
    process = subprocess.Popen([sys.executable, '-c', CHILD.format(configure=configure)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment)
    try:
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if selector.select(timeout=deadline - time.monotonic()):
                return process.stdout.readline()
        return None
    finally:
        process.kill()
        process.wait(timeout=10)


def test_line_buffered_console_delivers_progress_while_the_command_runs():
    assert _first_line_within('_line_buffer_console()') == b'Running: [1/1] progress line\n'


def test_a_pipe_is_block_buffered_without_it():
    # The defect this guards against: nothing arrives until the process exits.
    assert _first_line_within('', seconds=3.0) is None


def test_console_entry_point_line_buffers_before_dispatch(monkeypatch):
    import importlib
    # agentbench.cli re-exports a main() function under the module's own name.
    main = importlib.import_module('agentbench.cli.main')
    calls = []
    monkeypatch.setattr(main, '_line_buffer_console', lambda: calls.append('buffered'))
    monkeypatch.setattr(main, 'build_parser', lambda: (_ for _ in ()).throw(SystemExit(0)))
    try:
        main.cli(['sdk', 'list'])
    except SystemExit:
        pass
    assert calls == ['buffered']

"""Issue #44: the documented demo really completes without credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('directory', ['plain', '离线示例 with spaces'])
def test_offline_demo_without_environment_credentials(tmp_path, directory):
    root = Path(__file__).resolve().parents[1]
    working = tmp_path / directory
    working.mkdir()
    # Windows needs SystemRoot even when service credentials are deliberately absent.
    environment = {name: value for name, value in os.environ.items()
                   if name.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
    environment.update(PATH=os.defpath, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONIOENCODING='utf-8')
    result = subprocess.run([sys.executable, '-B', '-m', 'examples.offline_demo', '--output', str(working/'demo.json')],
                            cwd=working, env=environment, capture_output=True, text=True,
                            encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith('OFFLINE_RESULT='))
    events = json.loads(Path(line.split('=', 1)[1]).read_text(encoding='utf-8'))
    assert events[-1]['event'] == 'suite_completed'
    assert events[-1]['summary']['suite_passed'] is True


def test_offline_demo_runs_repeatedly_without_network_or_external_processes(tmp_path, monkeypatch):
    import socket
    import threading

    from examples.offline_demo import run_demo

    def forbidden(*args, **kwargs):
        raise AssertionError('The offline demo must not use network or external processes')

    # Windows implements asyncio's internal socketpair with a loopback connection.
    # Allow only socketpair construction, not connections made by the Agent/SDK.
    internal = threading.local()
    original_pair = socket.socketpair

    def socketpair(*args, **kwargs):
        internal.creating_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            internal.creating_pair = False

    def guard_connect(original):
        def connect(*args, **kwargs):
            if getattr(internal, 'creating_pair', False):
                return original(*args, **kwargs)
            return forbidden(*args, **kwargs)
        return connect

    monkeypatch.setattr(socket, 'socketpair', socketpair)
    monkeypatch.setattr(socket.socket, 'connect', guard_connect(socket.socket.connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guard_connect(socket.socket.connect_ex))
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.chdir(tmp_path)
    for name in ('KUMA_API_KEY', 'DEFUZEX_API_KEY', 'OPENROUTER_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    for index in range(2):
        execution = run_demo(tmp_path / f'demo-{index}.json')
        assert execution.exit_code == 0
        events = json.loads(execution.result_log.path.read_text(encoding='utf-8'))
        assert events[-1]['event'] == 'suite_completed'
        assert events[-1]['summary']['suite_passed'] is True

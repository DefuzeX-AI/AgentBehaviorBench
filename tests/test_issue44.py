"""Issue #44: the documented demo really completes without credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_offline_demo_without_environment_credentials(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = {'PATH': os.defpath, 'PYTHONPATH': str(root), 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-m', 'examples.offline_demo', '--output', str(tmp_path/'demo.json')],
                            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith('OFFLINE_RESULT='))
    events = json.loads(Path(line.split('=', 1)[1]).read_text())
    assert events[-1]['event'] == 'suite_completed'
    assert events[-1]['summary']['suite_passed'] is True

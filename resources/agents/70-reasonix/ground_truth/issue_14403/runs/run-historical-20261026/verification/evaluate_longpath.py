"""Host-only Windows long-path bridge; shared by both experimental arms."""
import subprocess
import sys
import runpy
from pathlib import Path

original_popen = subprocess.Popen

class DockerPathPopen(original_popen):
    def __init__(self, args, *positional, **kwargs):
        if isinstance(args, (list, tuple)) and Path(str(args[0])).name.lower() in ('docker', 'docker.exe'):
            args = [a.replace('\\\\?\\', '').replace('//?/', '') if isinstance(a, str) else a for a in args]
        super().__init__(args, *positional, **kwargs)

subprocess.Popen = DockerPathPopen
arm = sys.argv[1]
assert arm in ('before', 'after')
root = Path(__file__).resolve().parent
repo = root.parent.parent
sys.path.insert(0, str(repo))
result_root = '\\\\?\\' + str(root / (sys.argv[2] if len(sys.argv) > 2 else ('b' if arm == 'before' else 'a')))
sys.argv = ['agentbench', 'evaluate', f'verify-reasonix14403-{arm}', '--registry', str(root/'registry.toml'), '--env-file', str(repo/'.env'), '--sdk', 'native', '--case-file', str(root/'case.json'), '--cases', '1', '--max-steps', '1', '--case-retries', '0', '--no-view', '--results-dir', result_root, '-y']
runpy.run_module('agentbench', run_name='__main__')

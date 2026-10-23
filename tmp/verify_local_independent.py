import builtins, runpy, sys
sys.path.insert(0, str(__import__("pathlib").Path.cwd()))
original = builtins.__import__
def no_kuma(name, *args, **kwargs):
    if name == 'kuma' or name.startswith('kuma.'):
        raise RuntimeError('KUMA import forbidden during independent local acceptance')
    return original(name, *args, **kwargs)
builtins.__import__ = no_kuma
sys.argv = ['agentbench', 'evaluate', 'react-agent', '--sdk', 'local', '--case-file', 'results/verification/native-react-online/cases.json', '--cases', '1', '--max-steps', '2', '--results-dir', 'C:/Song_startup/benchmark/l', '--no-view', '-y']
from agentbench.cli.main import cli
cli()

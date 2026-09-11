"""Container-only acceptance: same interpreter, no SDK Run or model call."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys

assert Path('/.dockerenv').is_file(), 'Must run inside Docker'
assert os.getuid() != 0, 'Acceptance must run as non-root'
sys.path.insert(0, '/opt/agent/agent')
import kuma
from backend.graph import Graph
import backend.graph

assert callable(kuma.create_run)
assert callable(Graph.run)
assert Path(kuma.__file__).is_relative_to('/usr/local/lib')
assert Path(backend.graph.__file__).is_relative_to('/opt/agent/agent')
print(json.dumps({
    'status': 'passed', 'python': sys.executable, 'uid': os.getuid(),
    'sdk_distribution': 'kuma-defuzex',
    'sdk_version': importlib.metadata.version('kuma-defuzex'),
    'sdk_import': kuma.__file__, 'sdk_entry': 'kuma.create_run',
    'company_import': backend.graph.__file__, 'company_entry': 'backend.graph.Graph.run',
    'scope': 'imports only; no create_run, Graph instantiation, research, or judge',
}, ensure_ascii=False, indent=2))

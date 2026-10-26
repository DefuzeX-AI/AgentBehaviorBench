import json
import threading
import sys
from pathlib import Path
from zipfile import ZipFile
from agentbench.cli.viewer import start_viewer_server
p = Path('resources/agents/07-readwren/ground_truth/manifest.json')
d = json.loads(p.read_bytes())['defects'][0]
with ZipFile(p.parent / d['observations'][0]['evidence_path']) as z:
    path = Path(json.loads(z.read('suite/plan.json'))['result_log_path'])
viewer = start_viewer_server(path, port=int(sys.argv[1]) if len(sys.argv) > 1 else 54200)
print(viewer.url, flush=True)
threading.Event().wait()

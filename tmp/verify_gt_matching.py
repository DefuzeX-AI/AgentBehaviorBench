import json
from pathlib import Path
from zipfile import ZipFile
from agentbench.cli.environment import load_project_environment, execution_environment_snapshot
from agentbench.harness.ground_truth.evaluator import evaluate_suite

root = Path.cwd()
load_project_environment(None)
env = dict(execution_environment_snapshot().environ)
env['ABB_GT_MAX_CALLS'] = '20'
path = root / 'resources/agents/07-readwren/ground_truth/manifest.json'
defect = json.loads(path.read_text())['defects'][0]
with ZipFile(path.parent / defect['observations'][0]['evidence_path']) as archive:
    plan = json.loads(archive.read('suite/plan.json'))
directory = Path(plan['result_log_path']).parent
result = evaluate_suite(directory, root, environ=env)
print(json.dumps({'scores': result['scores'], 'calls': result['calls'], 'directory': str(directory)}, ensure_ascii=True))

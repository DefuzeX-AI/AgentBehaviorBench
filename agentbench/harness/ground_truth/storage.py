"""Agent-owned GT results; a Suite retains only checked relative references."""
import hashlib
import json
import os
from pathlib import Path

from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.common.artifacts import Artifacts


def agent_roots(directory, plan):
    if plan.get('artifact_layout') != 'agent-trajectories-v1':
        return {}
    store = FileArtifactStore(directory)
    return {a['agent_id']: store.agent_directory(a['agent_id']) / 'gt' / plan['suite_id']
            for a in plan['agents']}


def publish(directory, roots, summary, environ):
    refs = []
    for agent, root in roots.items():
        payload = {**summary, 'decisions': [r for r in summary['decisions'] if r['agent_id'] == agent],
                   'skipped_agents': [r for r in summary['skipped_agents'] if r['agent_id'] == agent]}
        relative = 'evaluations/' + summary['evaluation_id'] + '/result.json'
        Artifacts(root, environ=environ).save(relative, payload)
        path = root / relative
        refs.append({'agent_id': agent, 'path': os.path.relpath(path, directory).replace('\\', '/'),
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    Artifacts(directory, environ=environ).save('gt.json', {'schema': 'abb.gt.references.v1', 'references': refs})


def read(directory):
    path = directory / 'gt.json'
    if not path.is_file():
        return None
    data = json.loads(path.read_bytes())
    if data.get('schema') != 'abb.gt.references.v1':
        raise ValueError('Invalid GT references')
    result_root = directory.parent.parent if directory.parent.name == 'suites' else directory.parent
    values = []
    for ref in data['references']:
        path = (directory / ref['path']).resolve()
        if not path.is_relative_to(result_root / 'agents' / ref['agent_id']) or path.is_symlink():
            raise ValueError('GT reference leaves Agent artifacts')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('GT result digest mismatch')
        values.append(json.loads(raw))
    if not values:
        return None
    return {**values[0], 'decisions': [r for v in values for r in v['decisions']],
            'skipped_agents': [r for v in values for r in v['skipped_agents']]}

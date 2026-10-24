"""Suite journals contain scheduling metadata and checked Agent record references."""
import hashlib
import json
import os
from pathlib import Path

from .atomic import atomic_bytes

FIELDS = ('case_result', 'item', 'benchmark', 'artifacts', 'error')


def retain_event(directory, event, *, managed):
    if (not managed or not event.get('agent_id')
            or not any(isinstance(event.get(key), (dict, list)) for key in FIELDS)):
        return event
    from agentbench.sdk.integration.artifacts import FileArtifactStore
    root = FileArtifactStore(directory).agent_directory(event['agent_id']) / 'records'
    value = dict(event)
    for key in FIELDS:
        if not isinstance(value.get(key), (dict, list)):
            continue
        raw = json.dumps(value[key], ensure_ascii=False, indent=2).encode('utf-8')
        digest = hashlib.sha256(raw).hexdigest()
        path = root / (digest + '.json')
        if not path.exists():
            atomic_bytes(path, raw)
        value[key] = {'schema': 'abb.artifact-reference.v1',
            'path': os.path.relpath(path, directory).replace('\\', '/'), 'sha256': digest}
    return value


def expand_event(directory, event):
    value = dict(event)
    directory = Path(directory).resolve()
    root = directory.parent.parent if directory.parent.name == 'suites' else directory.parent
    for key in FIELDS:
        ref = value.get(key)
        if not isinstance(ref, dict) or ref.get('schema') != 'abb.artifact-reference.v1':
            continue
        path = (directory / ref['path']).resolve()
        if not path.is_relative_to(root / 'agents') or path.is_symlink():
            raise ValueError('Suite reference leaves Agent artifacts')
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('Linked Suite artifact reference')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('Suite artifact reference digest mismatch')
        value[key] = json.loads(raw)
    return value

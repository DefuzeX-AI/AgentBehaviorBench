"""Export repair inputs while keeping GT answers and provenance on the host."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from agentbench.harness.ground_truth.issues import read_issue
from agentbench.harness.registry import tomllib
from agentbench.harness.session.plan import source_digest
from agentbench.runtime.source.cache import source_archive
from agentbench.runtime.source.config import git_source_spec, source_spec
from agentbench.runtime.source.export import export_archive, export_digest
from agentbench.runtime.source.inventory import extract_source
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.native.backend import validate_case


def definition(root, agent_id, issue):
    if type(issue) is not int or issue < 1:
        raise ValueError('--issue must be a positive integer')
    _, _, document = read_issue(root, agent_id, f'issue_{issue}')
    revision = document.get('commit_version')
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-fA-F]{40}', revision):
        raise ValueError('Issue commit_version must be a full 40-character commit SHA')
    return document


def reproduction_case(document):
    steps = document.get('steps')
    if not isinstance(steps, list) or not steps or any(
            not isinstance(step, str) or not step.strip() for step in steps):
        raise ValueError('Issue requires nonempty string steps for its reproduction Case')
    return validate_case({'case_id': document.get('case_id') or 'issue-reproduction',
                         'inputs': [{'input_id': f'step-{i + 1}', 'payload': step}
                                    for i, step in enumerate(steps)]})


def export_project(engine, root, agent_id, issue, output, *, records_dir=None, output_fn=print, no_run=False):
    root = Path(root).resolve()
    output = Path(output)
    if not output.is_absolute():
        raise ValueError('--output must be an absolute path')
    output = output.resolve()
    if output.exists():
        raise ValueError('Output directory already exists; existing work will not be overwritten')
    if output.is_relative_to(root):
        raise ValueError('Export the repair project outside the ABB repository')
    parent = Path(records_dir).resolve() if records_dir else root.parent / 'outputs/exp3/projects'
    if parent.is_relative_to(output) or parent.is_relative_to(root):
        raise ValueError('Host records must remain outside the repair project and ABB repository')
    document = definition(root, agent_id, issue)
    if no_run:
        unit, _, _ = read_issue(root, agent_id, f'issue_{issue}')
        manifest = tomllib.loads((unit / 'agent.toml').read_text(encoding='utf-8'))
        spec = git_source_spec(manifest.get('source', {}).get('repository', ''), document['commit_version'])
        base_target = None
    else:
        target = engine.prepare(agent_id, document['commit_version'], output=output_fn)
        target.validate()
        if target.revision.lower() != document['commit_version'].lower():
            raise ValueError('Prepared target revision differs from Issue commit_version')
        spec = source_spec(tomllib.loads((target.registration.path / 'agent.toml').read_text(encoding='utf-8')))
        base_target = target.describe()
    # Export the original commit, without ABB installation overlays or history.
    submodules = []
    if no_run:
        archive, submodules = export_archive(spec, root / 'cache/sources', lambda: None, output_fn)
    else:
        archive = source_archive(spec, root / 'cache/sources', lambda: None, output_fn)
    output.mkdir(parents=True, exist_ok=False)
    source_path = output / 'source'
    if os.name == 'nt' and not str(source_path).startswith('\\\\?\\'):
        # Exact historical trees can contain paths longer than Win32 MAX_PATH.
        absolute = str(source_path)
        source_path = Path('\\\\?\\UNC\\' + absolute[2:] if absolute.startswith('\\\\') else '\\\\?\\' + absolute)
    extract_source(archive, source_path, lambda: None, allow_symlinks=no_run)
    (output / 'issue.json').write_text(json.dumps(document['issue'], ensure_ascii=False, indent=2) + '\n',
                                     encoding='utf-8')
    record = {'schema': 'abb.exp3.project.v1', 'agent_id': agent_id, 'issue_number': issue,
              'created_at': datetime.now(timezone.utc).isoformat(), 'directory': str(output),
              'source': str(output / 'source'), 'base_target': base_target,
              'no_run': no_run, 'repository': spec.repository, 'revision': spec.revision,
              'source_sha256': export_digest(source_path) if no_run else source_digest(source_path)}
    if no_run:
        record.update(source_digest_schema='abb.export-tree.v1', submodules=submodules)
    path = parent / ('project_' + uuid4().hex[:16])
    Artifacts(path, environ={}).save('project.json', record)
    return {**record, 'record_path': str(path / 'project.json')}

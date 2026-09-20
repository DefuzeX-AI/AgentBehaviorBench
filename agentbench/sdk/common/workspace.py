"""Explicit evaluation workspace policy shared by generation and execution."""
from dataclasses import dataclass, asdict
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil


@dataclass(frozen=True)
class WorkspacePolicy:
    path: str | None = None
    initial_state: str | None = None
    fixture: str | None = None
    track_files: bool = False
    upload_diff: bool = False
    export_changed_files: bool = False

    def as_dict(self):
        return asdict(self)


def workspace_policy(manifest):
    evaluation = manifest.get('evaluation', {})
    if not isinstance(evaluation, dict):
        raise ValueError('evaluation must be a table')
    workspace, evidence = evaluation.get('workspace', {}), evaluation.get('file_evidence', {})
    if not isinstance(workspace, dict) or not isinstance(evidence, dict):
        raise ValueError('evaluation workspace and file_evidence must be tables')
    if set(workspace) - {'path', 'initial_state', 'fixture'} or set(evidence) - {'track_files', 'upload_diff', 'export_changed_files'}:
        raise ValueError('Unknown evaluation workspace/file_evidence field')
    for name, value in evidence.items():
        if type(value) is not bool:
            raise ValueError(f'evaluation.file_evidence.{name} must be boolean')
    path = workspace.get('path')
    if workspace:
        if not isinstance(path, str) or not path.startswith('/') or PurePosixPath(path).as_posix() != path or '..' in PurePosixPath(path).parts:
            raise ValueError('Evaluation workspace needs a canonical absolute container path')
        parts = PurePosixPath(path).parts
        # Avoid masking installed code, container controls, or an entire HOME.
        if not ((len(parts) >= 4 and parts[1] == 'home') or (len(parts) >= 3 and parts[1] == 'workspace')):
            raise ValueError('Evaluation workspace must be a dedicated child of /home/<user> or /workspace')
        if workspace.get('initial_state') not in ('empty', 'fixture'):
            raise ValueError('Workspace initial_state must be empty or fixture')
        fixture = workspace.get('fixture')
        if workspace['initial_state'] == 'fixture':
            if not isinstance(fixture, str) or not fixture.startswith('evaluation/') or '..' in PurePosixPath(fixture).parts or PurePosixPath(fixture).as_posix() != fixture:
                raise ValueError('Workspace fixture must be a relative directory under evaluation/')
        elif fixture is not None:
            raise ValueError('Empty workspace cannot declare a fixture')
        if manifest.get('framework') == 'acp' and manifest.get('adapter', {}).get('cwd') != path:
            raise ValueError('ACP adapter.cwd must equal the evaluation workspace path')
    if any(evidence.values()) and not workspace:
        raise ValueError('File evidence requires an explicit evaluation workspace')
    if (evidence.get('upload_diff') or evidence.get('export_changed_files')) and not evidence.get('track_files'):
        raise ValueError('Diff upload and changed-file export require track_files')
    return WorkspacePolicy(**workspace, **evidence)


def prepare_workspace(root, destination, policy):
    """Copy declared initial state, with bounded regular files and no links."""
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    total = 0
    if policy.initial_state == 'fixture':
        source = root / policy.fixture
        if not source.is_dir() or any(p.is_symlink() for p in (source, *source.parents) if p.is_relative_to(root)):
            raise ValueError('Workspace fixture is missing or linked')
        for item in sorted(source.rglob('*')):
            relative = item.relative_to(source)
            if item.is_symlink() or '.kuma' in relative.parts or '.git' in relative.parts:
                raise ValueError('Workspace fixture cannot contain links or runtime state')
            target = destination / relative
            if item.is_dir():
                target.mkdir(exist_ok=True)
                continue
            if not item.is_file():
                raise ValueError('Workspace fixture must contain regular files')
            total += item.stat().st_size
            if total > 32 * 1024 * 1024 or len(entries) >= 10000:
                raise ValueError('Workspace fixture exceeds 32 MiB or 10000 files')
            data = item.read_bytes()
            entries.append((relative.as_posix(), hashlib.sha256(data).hexdigest()))
            target.write_bytes(data)
            shutil.copymode(item, target)
    # KUMA otherwise changes .gitignore at create_run, perturbing initial state.
    ignore = destination / '.gitignore'
    previous = ignore.read_text() if ignore.exists() else ''
    if '/.kuma/' not in previous.splitlines():
        ignore.write_text(previous + '\n/.kuma/\n')
    return {'schema': 'abb.workspace.v1', 'path': policy.path,
            'initial_state': policy.initial_state,
            'fixture_sha256': hashlib.sha256(json.dumps(entries, separators=(',', ':')).encode()).hexdigest()}


def workspace_digest(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

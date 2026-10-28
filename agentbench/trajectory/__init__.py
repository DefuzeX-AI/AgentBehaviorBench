"""The trajectory evidence contract: build, persist and read trajectory.json.

The raw execution records remain the source of truth. A trajectory is derived
from them once, validated, and saved beside them so every result package can be
read as a step sequence without re-parsing traces.
"""
import hashlib
import json
from pathlib import Path

from .schema import SCHEMA, validate
from .builder import build

FILENAME = 'trajectory.json'


def _project_root():
    try:
        from agentbench.project import project_root
        return project_root()
    except Exception:  # The builder only uses the root for optional unit metadata.
        return None


def read(directory):
    """The saved trajectory, validated; None when the package has none."""
    path = Path(directory) / FILENAME
    if not path.is_file() or path.is_symlink():
        return None
    return validate(json.loads(path.read_text(encoding='utf-8')))


def load(directory, *, environ=None, project_root=None):
    """Prefer the saved file; derive in memory for historical packages."""
    saved = read(directory)
    if saved is not None:
        return saved
    value = build(directory, environ=environ, project_root=project_root if project_root is not None else _project_root())
    value['derived_on_read'] = True
    return validate(value)


def write(directory, *, environ=None, project_root=None):
    """Always leave a trajectory.json behind; failures are recorded, not raised."""
    from agentbench.sdk.common.artifacts import Artifacts
    root = Path(directory)
    files = Artifacts(root, environ=environ)
    try:
        value = validate(build(root, environ=environ,
                               project_root=project_root if project_root is not None else _project_root()))
    except Exception as exc:  # noqa: BLE001 - the execution outcome must not change
        run = {}
        try:
            run = json.loads((root / 'run.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        value = {'schema': SCHEMA, 'status': 'failed', 'run_id': run.get('run_id') or root.name,
                 'agent_id': run.get('agent_id') or 'unknown', 'error_type': type(exc).__name__, 'error': str(exc)}
    files.save(FILENAME, value)
    raw = (root / FILENAME).read_bytes()
    return {'status': value['status'], 'path': FILENAME, 'sha256': hashlib.sha256(raw).hexdigest(),
            'steps': len(value.get('steps') or [])}


__all__ = ['SCHEMA', 'FILENAME', 'build', 'read', 'load', 'write', 'validate']

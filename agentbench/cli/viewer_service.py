"""Find an already running local project viewer for CLI deep links."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from agentbench.harness.session.atomic import atomic_json

SCHEMA = 'abb.viewer.service.v1'


def project_identity(root):
    return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()


def publish(root, base_url, instance_id):
    atomic_json(Path(root) / 'cache/viewer-service.json', {
        'schema': SCHEMA, 'project': project_identity(root),
        'base_url': base_url, 'instance_id': instance_id})


def find_viewer(root):
    """Probe only a loopback origin and require this project's live instance ID."""
    try:
        record = json.loads((Path(root) / 'cache/viewer-service.json').read_text())
        if not isinstance(record, dict):
            return None
        url = record['base_url']
        parsed = urlparse(url)
        if (record.get('schema') != SCHEMA or record.get('project') != project_identity(root)
                or parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
            return None
        with urlopen(url.rstrip('/') + '/api/health', timeout=1) as response:
            health = json.loads(response.read(8192))
        if (isinstance(health, dict) and health.get('schema') == SCHEMA and health.get('project') == record['project']
                and health.get('instance_id') == record['instance_id']):
            return url.rstrip('/')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def unpublish(root, instance_id):
    path = Path(root) / 'cache/viewer-service.json'
    try:
        record = json.loads(path.read_text())
        if isinstance(record, dict) and record.get('instance_id') == instance_id:
            path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass

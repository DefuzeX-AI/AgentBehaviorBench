"""Public, allowlisted Agent introduction from the current local registry."""
from pathlib import Path
import re
import yaml
import json
import hashlib
from agentbench.harness.registry import tomllib


def agent_profile(root, agent_id):
    root = Path(root).resolve()
    registry = tomllib.loads((root / 'resources/registry.toml').read_text(encoding='utf-8'))
    entry = next(row for row in registry['agents'] if row['agent_id'] == agent_id)
    unit = (root / entry['path']).resolve()
    if not unit.is_relative_to(root):
        raise ValueError('Agent outside project')
    def read(name):
        file = (unit / name).resolve()
        if not file.is_relative_to(unit) or file.stat().st_size > 131072:
            raise ValueError('Invalid profile file')
        return file.read_text(encoding='utf-8')
    manifest = tomllib.loads(read('agent.toml'))
    if manifest.get('agent_id') != agent_id:
        raise ValueError('Agent identity mismatch')
    source = manifest.get('source', {})
    strategy_group = None
    profile_warning = None
    try:
        text = read('requirement.md')
        front = re.match(r'\A---\s*\n(.*?)\n---\s*\n', text, re.S)
        description = text[front.end():] if front else text
        if front:
            try:
                metadata = yaml.safe_load(front[1])
                group = metadata.get('strategy_group') if isinstance(metadata, dict) else None
                if isinstance(group, dict) and all(isinstance(group.get(key), str) for key in ('schema_version', 'id', 'version')):
                    strategy_group = {key: group[key] for key in ('schema_version', 'id', 'version')}
                elif group is not None:
                    profile_warning = 'Strategy Group declaration is invalid.'
            except yaml.YAMLError:
                profile_warning = 'Agent profile front matter could not be read.'
    except FileNotFoundError:
        description = ''
    from agentbench.sdk.strategy_checks import snapshot_path
    strategy_check = None
    try:
        saved = json.loads(snapshot_path(root, unit).read_text(encoding='utf-8'))
        fingerprint = hashlib.sha256((unit / 'requirement.md').read_bytes()).hexdigest()
        if saved.get('profile_sha256') == fingerprint:
            strategy_check = {key: saved.get(key) for key in ('status', 'id', 'version', 'display_name', 'reason', 'checked_at', 'sdk', 'catalog_release')}
    except (OSError, ValueError, AttributeError):
        pass
    return {'agent_id': agent_id, 'display_name': manifest.get('display_name', agent_id),
            'framework': manifest.get('framework'), 'runtime': manifest.get('runtime', {}).get('type'),
            'repository': source.get('repository'), 'revision': source.get('revision'),
            'description': description, 'strategy_group': strategy_group, 'strategy_check': strategy_check, 'profile_warning': profile_warning,
            'provenance': 'Current local Agent profile'}

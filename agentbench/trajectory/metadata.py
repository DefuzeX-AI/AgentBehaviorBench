"""Freeze the Agent unit an attempt runs into ``request/target.json``."""
import hashlib
import json
from pathlib import Path


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capture_target(unit):
    """Freeze the actual execution unit before staging; never consult the registry."""
    from agentbench.harness.registry import tomllib
    unit = Path(unit)
    manifest = tomllib.loads((unit / 'agent.toml').read_text(encoding='utf-8'))
    if manifest.get('framework') == 'langgraph' and manifest.get('runtime', {}).get('type') == 'docker':
        from agentbench.harness.otel.config import parse_config
        if parse_config(manifest).profile == 'langfuse-auto':
            manifest.setdefault('atif', {}).setdefault('source', 'langfuse')
    source = manifest.get('source') or {}
    architecture = {'source_revision': source.get('revision') or source.get('sha256')}
    for key, name in (('profile', 'requirement.md'), ('manifest', 'agent.toml')):
        if (unit / name).is_file():
            architecture[key] = {'path': name, 'sha256': _sha256(unit / name)}
    binding = (manifest.get('adapter') or {}).get('binding')
    if isinstance(binding, str):
        name = 'bindings/' + binding.split(':', 1)[0]
        path = unit / name
        if path.resolve().is_relative_to(unit.resolve()) and path.is_file():
            architecture['binding'] = {'path': name, 'sha256': _sha256(path)}
    if (unit / 'provenance.json').is_file():
        architecture['prepared_target'] = json.loads((unit / 'provenance.json').read_text(encoding='utf-8'))
    return {'schema': 'abb.target.snapshot.v1',
            'runtime': {key: manifest[key] for key in
                        ('framework', 'runtime', 'adapter', 'launch', 'evaluation', 'atif') if key in manifest},
            'architecture': architecture}

"""Task, agent configuration and architecture references for one attempt.

Only recorded facts are used: the Case and first Input, the first model request,
and the registered Agent unit when the project root is available.
"""
import hashlib
import json
from pathlib import Path


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _system_prompt(first_input):
    if not isinstance(first_input, dict):
        return None
    if isinstance(first_input.get('system'), (str, list)):
        return first_input['system']
    if isinstance(first_input.get('instructions'), str):
        return first_input['instructions']
    for message in first_input.get('messages') or []:
        if isinstance(message, dict) and message.get('role') in ('system', 'developer'):
            return message.get('content')
        if isinstance(message, dict) and message.get('type') == 'system':
            return message.get('content')
    return None


def _unit(agent_id, project_root):
    if project_root is None:
        return None
    try:
        from agentbench.harness.ground_truth.manifests import registered_units
        units, _, _ = registered_units(project_root)
    except Exception:  # Registry problems never block trajectory generation.
        return None
    return units.get(agent_id)


def build_metadata(api, *, agent_id, framework, first_input, actors, project_root=None):
    case = api.read('case.json') or api.read('evaluation/case.json') or {}
    inputs = case.get('inputs') if isinstance(case, dict) else None
    task = None
    if isinstance(inputs, list) and inputs and isinstance(inputs[0], dict):
        task = inputs[0].get('payload')
    if task is None:
        first = api.read(f'{api.outputs()[0]}/input.json') if api.outputs() else None
        task = first.get('payload') if isinstance(first, dict) else None
    configuration = {'agents': [{'agent_name': name} for name in actors],
                     'system_prompt': _system_prompt(first_input),
                     'tools': (first_input or {}).get('tools') if isinstance(first_input, dict) else None}
    architecture = {'framework': framework}
    frozen = api.read('request/target.json')
    warnings = []
    if frozen is None:
        unit = _unit(agent_id, project_root)
        if unit is not None:
            try:
                frozen = capture_target(unit)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                warnings.append(f'Agent unit metadata unavailable: {type(exc).__name__}')
        else:
            warnings.append('Agent unit not registered; architecture references omitted')
    if frozen is not None:
        configuration['runtime'] = frozen['runtime']
        architecture.update(frozen['architecture'])
    return {'task_instruction': task, 'case_id': case.get('case_id') if isinstance(case, dict) else None,
            'agent_configuration': configuration, 'system_architecture': architecture}, warnings


def capture_target(unit):
    """Freeze the actual execution unit before staging; never consult the registry."""
    from agentbench.harness.registry import tomllib
    unit = Path(unit)
    manifest = tomllib.loads((unit / 'agent.toml').read_text(encoding='utf-8'))
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
                        ('framework', 'runtime', 'adapter', 'launch', 'evaluation') if key in manifest},
            'architecture': architecture}

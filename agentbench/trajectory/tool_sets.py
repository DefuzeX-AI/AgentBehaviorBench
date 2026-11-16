"""Store identical tool lists once and restore them for trajectory readers."""

import json
from copy import deepcopy


def _tool_owners(value):
    configuration = value.get('metadata', {}).get('agent_configuration')
    if isinstance(configuration, dict):
        yield configuration
    for step in value.get('steps', []):
        if step['kind'] == 'model':
            yield step['input']


def encode(value):
    stored = deepcopy(value)
    tool_sets, references = {}, {}
    for owner in _tool_owners(stored):
        tools = owner.get('tools')
        if not isinstance(tools, list):
            continue
        key = json.dumps(tools, ensure_ascii=True, separators=(',', ':'))
        ref = references.get(key)
        if ref is None:
            ref = f'tools_{len(tool_sets) + 1}'
            references[key] = ref
            tool_sets[ref] = tools
        del owner['tools']
        owner['tools_ref'] = ref
    if tool_sets:
        stored['tool_sets'] = tool_sets
    return stored


def expand(value):
    tool_sets = value.pop('tool_sets', {})
    if not isinstance(tool_sets, dict) or any(not isinstance(tools, list) for tools in tool_sets.values()):
        raise ValueError('Invalid trajectory: tool_sets must map references to tool lists')
    for owner in _tool_owners(value):
        if 'tools_ref' not in owner:
            continue
        ref = owner.pop('tools_ref')
        if 'tools' in owner or not isinstance(ref, str) or ref not in tool_sets:
            raise ValueError('Invalid trajectory: conflicting or unresolved tools_ref')
        owner['tools'] = deepcopy(tool_sets[ref])
    return value

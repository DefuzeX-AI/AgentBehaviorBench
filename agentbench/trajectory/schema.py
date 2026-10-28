"""The abb.agent-trajectory.v1 contract: a flat, self-contained step sequence.

Every step records the acting component, the complete input it received, the
complete output it produced, and the tool logs it caused. Evidence references
only point back at the raw files; reading a trajectory never requires them.
"""

SCHEMA = 'abb.agent-trajectory.v1'
BUILDER_VERSION = 1
STATUSES = ('complete', 'partial', 'failed')
STEP_KINDS = ('model', 'tool_only')
TOOL_STATUSES = ('succeeded', 'error', 'not_observed')
LINKS = ('exact', 'ambiguous', 'none')


def _require(condition, message):
    if not condition:
        raise ValueError('Invalid trajectory: ' + message)


def validate(value):
    """Check structure and identities; content values are opaque evidence."""
    _require(isinstance(value, dict), 'expected an object')
    _require(value.get('schema') == SCHEMA, 'unknown schema')
    _require(value.get('status') in STATUSES, 'unknown status')
    for key in ('run_id', 'agent_id'):
        _require(isinstance(value.get(key), str) and value[key], f'{key} must be a non-empty string')
    if value['status'] == 'failed':
        _require(isinstance(value.get('error'), str), 'failed trajectory needs an error')
        return value
    _require(isinstance(value.get('metadata'), dict), 'metadata must be an object')
    _require(isinstance(value.get('steps'), list), 'steps must be a list')
    _require(isinstance(value.get('inputs'), list), 'inputs must be a list')
    _require(isinstance(value.get('coverage'), dict), 'coverage must be an object')
    _require(isinstance(value.get('sources'), list), 'sources must be a list')
    _require(isinstance(value.get('warnings'), list), 'warnings must be a list')
    ordinals = {item.get('ordinal') for item in value['inputs'] if isinstance(item, dict)}
    for index, step in enumerate(value['steps'], 1):
        _require(isinstance(step, dict), f'step {index} is not an object')
        _require(step.get('step_id') == index, f'step {index} has step_id {step.get("step_id")!r}')
        _require(step.get('kind') in STEP_KINDS, f'step {index} has unknown kind')
        _require(isinstance(step.get('agent_name'), str) and step['agent_name'], f'step {index} has no agent_name')
        _require(step.get('input_ordinal') is None or step['input_ordinal'] in ordinals,
                 f'step {index} references an unknown input')
        if step['kind'] == 'model':
            _require(isinstance(step.get('input'), dict), f'step {index} has no input')
            _require(isinstance(step.get('output'), dict), f'step {index} has no output')
        _require(isinstance(step.get('tool_logs'), list), f'step {index} has no tool_logs list')
        for log in step['tool_logs']:
            _require(isinstance(log, dict) and isinstance(log.get('tool_name'), str), f'step {index} has an invalid tool log')
            _require(log.get('execution_status') in TOOL_STATUSES, f'step {index} tool log has unknown status')
            _require(log.get('link') in LINKS, f'step {index} tool log has unknown link')
    for item in value['inputs']:
        _require(isinstance(item, dict) and isinstance(item.get('ordinal'), str), 'input entries need an ordinal')
        span = item.get('step_range')
        _require(span is None or (isinstance(span, list) and len(span) == 2
                 and all(type(v) is int for v in span) and 0 <= span[0] <= span[1] <= len(value['steps'])),
                 f'input {item.get("ordinal")} has an invalid step_range')
    return value


def step_ids(value):
    return [step['step_id'] for step in value.get('steps', [])]

"""Select model calls and tool executions from the recorded interaction index.

Pairing follows recorded identifiers only: the interceptor call id, the
framework span id carried in request headers, and tool call ids emitted by the
model. Timestamps never create relationships.
"""
from .content import exit_status


def _data(record):
    value = (record or {}).get('raw', {}).get('data') if record else None
    return value if isinstance(value, dict) else {}


def _event(record):
    return (record or {}).get('raw', {}).get('event') if record else None


def wire_calls(index):
    return [row for row in index.rows if row['kind'] == 'chat' and row.get('_request')]


def framework_calls(index):
    return [row for row in index.rows if row['kind'] == 'callback' and _data(row.get('_request')).get('kind') == 'llm']


def tool_rows(index):
    return [row for row in index.rows if row['kind'] == 'tool']


def wire_stream(records):
    """Native SSE payloads for one indexed call, in recorded sequence order.

    Match the desktop projection: replaying a sequence replaces that frame,
    while distinct call IDs are already isolated by the interaction index.
    Transport chunk metrics are never interpreted as content.
    """
    frames = {}
    for record in records:
        data = _data(record)
        sequence = data.get('sequence')
        if _event(record) == 'llm_delta' and type(sequence) is int and sequence > 0:
            frames[sequence] = data.get('payload')
    return {'events': [value for _, value in sorted(frames.items())]} if frames else None


def tool_log(index, row):
    """One tool execution: latest arguments, final outcome and terminal exit status."""
    records = index.groups.get(row['id'], [])
    start = _data(row.get('_request'))
    arguments = start.get('input')
    for record in records:
        if _event(record) in ('span_start', 'span_update') and 'input' in _data(record):
            arguments = _data(record)['input']
    end = next((r for r in reversed(records) if _event(r) == 'span_end'), None)
    error = next((r for r in reversed(records) if _event(r) == 'span_error'), None)
    control = next((r for r in reversed(records) if _event(r) == 'span_control'), None)
    outputs = _data(end).get('output') if end else None
    if error is not None:
        status, outputs = 'error', _data(error).get('error') if outputs is None else outputs
    elif end is None:
        status = 'not_observed'
    elif _data(end).get('tool_status') == 'error' or row.get('status') == 'failed':
        status = 'error'
    else:
        status = 'succeeded'
    log = {'tool_call_id': row.get('tool_call_id'), 'tool_name': start.get('name') or row.get('title'),
           'input_arguments': arguments, 'outputs': outputs, 'execution_status': status,
           'exit_status': exit_status(outputs), 'link': 'none',
           'started_at': row.get('timestamp'), 'ended_at': row.get('ended'),
           'evidence': {'interaction_id': row['id'], 'framework_span_id': row.get('framework_span_id')}}
    if control is not None:
        log['control'] = _data(control).get('control')
    return log

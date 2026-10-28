"""Select model calls and tool executions from the recorded interaction index.

Pairing follows recorded identifiers only: the interceptor call id, the
framework span id carried in request headers, and tool call ids emitted by the
model. Timestamps order steps; they never create relationships.
"""
from agentbench.observe.interactions import stamp

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


def llm_record(row, event):
    """The framework span_start/span_end record linked to a wire call, if any."""
    records = row.get('_callbacks') or []
    if not any(_event(r) == 'span_start' and _data(r).get('kind') == 'llm' for r in records):
        return None
    return next((r for r in reversed(records) if _event(r) == event), None)


def node_tool_calls(index, parent_span_id):
    """Tool calls in the graph node's own output when the model span lost them.

    Streamed LangChain generations keep no tool_calls; the enclosing node span
    (parent of the model span) still records the AI message the graph appended.
    """
    if not parent_span_id:
        return []
    for row in index.rows:
        if row['kind'] != 'callback' or row.get('framework_span_id') != parent_span_id:
            continue
        end = next((r for r in reversed(index.groups.get(row['id'], [])) if _event(r) == 'span_end'), None)
        output = _data(end).get('output') if end else None
        calls = []
        for update in output if isinstance(output, list) else [output]:
            value = update.get('update') if isinstance(update, dict) and isinstance(update.get('update'), dict) else update
            messages = value.get('messages') if isinstance(value, dict) else None
            for message in messages if isinstance(messages, list) else []:
                if isinstance(message, dict) and message.get('type') == 'ai':
                    for call in message.get('tool_calls') or []:
                        if isinstance(call, dict) and call.get('id'):
                            calls.append({'id': call['id'], 'name': call.get('name'), 'arguments': call.get('args')})
        return calls
    return []


def order_key(row):
    at = stamp(row.get('timestamp'))
    return (0 if at is not None else 1, at if at is not None else 0.0, row['id'])


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

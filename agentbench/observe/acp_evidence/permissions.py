"""Bounded projection of an ACP permission request and the client's answer.

The Agent asks through ``session/request_permission``; ABB answers by its
configured policy, never a person. Both sides become the arguments and result
of one tool span, the only content an evaluation SDK Judge receives from a
trace. Full protocol events stay in the local ``acp-events.jsonl``.
"""
import json
from agentbench.observe.store import json_value, redact

METHOD = 'session/request_permission'
SPAN_NAME = 'acp.' + METHOD
MAX_TEXT = 1024
MAX_ITEMS = 16
MAX_RAW_INPUT_BYTES = 4096


def _text(value):
    if not isinstance(value, str):
        return None
    return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + '…'


def _fields(source, keys):
    return {key: text for key in keys if (text := _text(source.get(key))) is not None}


def _option(value):
    if isinstance(value, dict):
        return _fields(value, ('optionId', 'name', 'kind'))
    return {'optionId': text} if (text := _text(value)) is not None else {}


def _tool_call(value):
    if not isinstance(value, dict):
        return {}
    call = _fields(value, ('toolCallId', 'title', 'kind', 'status'))
    locations = [item['path'] for item in value.get('locations') or ()
                 if isinstance(item, dict) and isinstance(item.get('path'), str)]
    if locations:
        call['locations'] = [_text(path) for path in locations[:MAX_ITEMS]]
        if len(locations) > MAX_ITEMS:
            call['locations_omitted'] = len(locations) - MAX_ITEMS
    if 'rawInput' in value:
        raw = value['rawInput']
        size = len(json.dumps(raw, ensure_ascii=False, default=str).encode('utf-8'))
        if size <= MAX_RAW_INPUT_BYTES:
            call['rawInput'] = raw
        else:
            call['rawInput_omitted'] = 'size_limit'
    if isinstance(value.get('content'), list) and value['content']:
        # Diffs and terminal content can be large; the tool span keeps them.
        call['content_items'] = len(value['content'])
    return call


def permission_evidence(data, secrets=()):
    """Return (request, decision) for one emitted ``permission`` event."""
    data = redact(json_value(data), secrets)
    options = [option for item in (data.get('options') or [])[:MAX_ITEMS] if (option := _option(item))]
    request = {'method': METHOD, 'requested_by': 'target_agent',
               'tool_call': _tool_call(data.get('tool_call')), 'options': options}
    if len(data.get('options') or []) > MAX_ITEMS:
        request['options_omitted'] = len(data['options']) - MAX_ITEMS
    outcome = data.get('outcome') if isinstance(data.get('outcome'), dict) else {}
    selected = _text(outcome.get('optionId'))
    chosen = next((item for item in options if item.get('optionId') == selected), {})
    decision = {'decided_by': _text(data.get('decided_by')) or 'abb_permission_policy',
                'automatic': True, 'policy': _text(data.get('policy')),
                'outcome': _text(outcome.get('outcome')) or 'not_observed'}
    if selected is not None:
        decision.update(selected_option_id=selected,
                        **{f'selected_option_{key}': chosen[key] for key in ('kind', 'name') if key in chosen})
    decision['note'] = ('ABB answered this permission request automatically under its configured '
                        'permission policy; no user reviewed or approved it.')
    return request, decision

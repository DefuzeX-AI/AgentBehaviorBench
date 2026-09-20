"""Join native logical calls to wire responses by explicit provider response IDs."""


def response_ids(payload):
    if not isinstance(payload, dict):
        return set()
    result = {payload['id']} if isinstance(payload.get('id'), str) else set()
    for event in payload.get('events', []) if isinstance(payload.get('events'), list) else []:
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'message_start':
            result.update(response_ids(event.get('message')))
        elif event.get('type') in ('response.created', 'response.completed'):
            result.update(response_ids(event.get('response')))
        elif isinstance(event.get('choices'), list):
            result.update(response_ids(event))
    return result


def link_native_calls(rows, contexts):
    native = []
    for row in rows:
        record = row.get('_request')
        if record and record['raw'].get('event') == 'native_model_call':
            native.append((row, record['raw']['data']))
    wire = [row for row in rows if row['kind'] == 'chat']
    ids = {row['id']: response_ids((row.get('_response') or {}).get('raw', {}).get('data', {}).get('payload')) for row in wire}
    for row in wire:
        matches = [(owner, call) for owner, call in native
                   if call.get('native_response_id') in ids[row['id']]
                   and owner.get('case_id') == row.get('case_id')]
        if not matches:
            continue
        unique_wire = sum(bool(ids[row['id']] & ids[other['id']]) and other.get('case_id') == row.get('case_id') for other in wire)
        owner, call = matches[0]
        if (len(matches) != 1 or unique_wire != 1 or
                (row.get('input_id') and row['input_id'] != owner.get('input_id'))):
            row.update(association_status='ambiguous', input_id=None, link_evidence=None, _context=None)
            continue
        context = contexts.get(owner.get('_context'))
        if context:
            row.update(input_id=context['input_id'], case_id=context['case_id'],
                association_status='input_exact', link_evidence='native_response_id',
                native_call_id=call.get('native_call_id'), native_turn_id=call.get('native_turn_id'),
                native_session_id=call.get('native_session_id'), purpose=call.get('purpose', 'unknown'),
                artifact_directory=context['folder'], _context=context['folder'])

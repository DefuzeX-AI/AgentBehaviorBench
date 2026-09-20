"""Derived, scoped emitted-tool relationships; never internal model spans.

Only protocol-defined response positions are inspected. Request history and
arbitrary tool arguments are deliberately excluded from identity extraction.
"""


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

def emitted_tool_ids(payload):
    if not isinstance(payload, dict):
        return set()
    found = set()
    def add(value):
        if isinstance(value, str) and value:
            found.add(value)
    def block(value):
        if isinstance(value, dict) and value.get('type') == 'tool_use':
            add(value.get('id'))
    for item in _objects(payload.get('content')):
        block(item)
    block(payload.get('content_block'))
    for choice in _objects(payload.get('choices')):
        if not isinstance(choice.get('message') or choice.get('delta') or {}, dict):
            continue
        for item in _objects((choice.get('message') or choice.get('delta') or {}).get('tool_calls')):
            add(item.get('id'))
    for item in _objects(payload.get('output')):
        if item.get('type') == 'function_call':
            add(item.get('call_id'))
    item = payload.get('item')
    if isinstance(item, dict) and item.get('type') == 'function_call':
        add(item.get('call_id'))
    for event in _objects(payload.get('events')):
        found.update(emitted_tool_ids(event))
    if isinstance(payload.get('response'), dict):
        found.update(emitted_tool_ids(payload['response']))
    return found


def link_tools(rows, contexts):
    """The containing artifact directory is the run scope; reject finer conflicts."""
    tools = [r for r in rows if r['kind'] == 'tool' and r.get('tool_call_id')]
    emissions = {}
    for row in rows:
        if row['kind'] == 'chat' and row.get('_response'):
            emissions[row['id']] = emitted_tool_ids((row['_response']['raw'].get('data') or {}).get('payload'))
    for row in rows:
        if row['kind'] != 'chat':
            continue
        record = row.get('_response')
        payload = (record['raw'].get('data') or {}).get('payload') if record else None
        identifiers = emitted_tool_ids(payload)
        relations = []
        for identifier in sorted(identifiers):
            candidates = [tool for tool in tools if tool['tool_call_id'] == identifier
                          and tool.get('case_id') == row.get('case_id')
                          and all(not row.get(key) or not tool.get(key) or row[key] == tool[key]
                                  for key in ('attempt_id', 'native_session_id'))]
            emitters = [r for r in rows if identifier in emissions.get(r['id'], set())
                        and r.get('case_id') == row.get('case_id')
                        and all(not row.get(key) or not r.get(key) or row[key] == r[key]
                                for key in ('attempt_id', 'native_session_id'))]
            relations.append({'type': 'emitted_tool', 'tool_call_id': identifier,
                'status': 'ambiguous' if len(emitters) > 1 or len(candidates) > 1 else 'exact' if candidates else 'unobserved',
                'interaction_ids': [tool['id'] for tool in candidates]})
        row['tool_relations'] = relations
        row['association_rule_version'] = 1
        if not relations:
            continue
        if any(link['status'] != 'exact' for link in relations):
            if not row.get('input_id') and any(link['status'] == 'ambiguous' for link in relations):
                row['association_status'] = 'ambiguous'
            continue
        folders = {tool['_context'] for tool in tools
                   if any(tool['id'] in link['interaction_ids'] for link in relations)}
        if len(folders) != 1:
            row['association_status'] = 'ambiguous'
            continue
        folder = next(iter(folders)); context = contexts.get(folder)
        if context and not row.get('input_id'):
            row.update(input_id=context['input_id'], case_id=context['case_id'],
                association_status='input_exact', link_evidence='emitted_tool_id',
                artifact_directory=folder, _context=folder)

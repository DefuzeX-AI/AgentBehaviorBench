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


SCOPE_KEYS = ('run_id', 'case_id', 'attempt_id', 'input_id', 'invocation_id', 'native_session_id')


def compatible(left, right, *, scope_keys=SCOPE_KEYS):
    """Missing identity is unknown; contradictory recorded identity never matches."""
    return not (left.get('identity_conflicts') or right.get('identity_conflicts')) and all(
        not left.get(key) or not right.get(key) or left[key] == right[key] for key in scope_keys)


def resolve_tools(models, tools, *, scope_keys=SCOPE_KEYS):
    """One rule for offline exports and live projections. IDs are scoped, not names."""
    result = {}
    for model in models:
        relations = []
        identifiers = model.get('emitted_tool_ids', [])
        for identifier in (sorted(identifiers) if isinstance(identifiers, set) else dict.fromkeys(identifiers)):
            candidates = [tool for tool in tools if tool.get('tool_call_id') == identifier
                          and compatible(model, tool, scope_keys=scope_keys)]
            # Count all possible owners of each execution too: incomplete scope must
            # not let two otherwise disjoint model calls both claim the same tool.
            emitters = [other for other in models if identifier in other.get('emitted_tool_ids', [])
                        and (compatible(model, other, scope_keys=scope_keys) or any(compatible(other, tool, scope_keys=scope_keys) for tool in candidates))]
            relations.append({'type': 'emitted_tool', 'tool_call_id': identifier,
                'status': 'ambiguous' if len(emitters) > 1 or len(candidates) > 1 else 'exact' if candidates else 'unobserved',
                'interaction_ids': [tool['id'] for tool in candidates]})
        result[model['id']] = relations
    return result


def link_tools(rows, contexts):
    """The containing artifact directory is the run scope; reject finer conflicts."""
    tools = [r for r in rows if r['kind'] == 'tool' and r.get('tool_call_id')]
    models = []
    for row in rows:
        if row['kind'] == 'chat' and row.get('_response'):
            models.append({**row, 'emitted_tool_ids': emitted_tool_ids(
                (row['_response']['raw'].get('data') or {}).get('payload'))})
    links = resolve_tools(models, tools)
    for row in rows:
        if row['kind'] != 'chat':
            continue
        relations = links.get(row['id'], [])
        row['tool_relations'] = relations
        row['association_rule_version'] = 2
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

import json
from agentbench.observe.interactions import interactions
from agentbench.observe.tool_links import emitted_tool_ids


def fixture(root, *, history=False, duplicate=False, wrong_case=False, repeated_response=False):
    folder = root / 'evaluation/inputs/0001'; folder.mkdir(parents=True)
    (folder / 'input.json').write_text(json.dumps({'case_id': 'case-a', 'input_id': 'step-1'}))
    tool = {'event': 'span_start', 'data': {'kind': 'tool', 'span_id': 'span-1',
        'tool_call_id': 'call-1', 'case_id': 'case-a'}}
    (folder / 'framework.jsonl').write_text(json.dumps(tool))
    if duplicate:
        other = root / 'evaluation/inputs/0002'; other.mkdir()
        (other / 'input.json').write_text(json.dumps({'case_id': 'case-a', 'input_id': 'step-2'}))
        tool['data']['span_id'] = 'span-2'
        (other / 'framework.jsonl').write_text(json.dumps(tool))
    content = {'content': [{'type': 'tool_use', 'id': 'call-1'}]}
    case = 'case-b' if wrong_case else 'case-a'
    rows = [{'event': 'llm_request', 'data': {'call_id': 'http-1', 'case_id': case,
             'payload': content if history else {}}},
            {'event': 'llm_response', 'data': {'call_id': 'http-1', 'case_id': case,
             'payload': {} if history else content}}]
    if repeated_response:
        rows += [{**r, 'data': {**r['data'], 'call_id': 'http-2'}} for r in rows[:]]
    (root / 'network.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    return interactions(root, {'kinds': 'chat'})


def test_current_response_links_without_fabricating_llm_span(tmp_path):
    result = fixture(tmp_path); row, = result['items']
    assert row['input_id'] == 'step-1'
    assert row['link_evidence'] == 'emitted_tool_id'
    assert row['framework_span_id'] is None
    assert result['correlation']['model']['emitted_tool_links'] == 1
    assert result['correlation']['model']['framework_linked'] == 0


def test_history_does_not_assign_current_input(tmp_path):
    row, = fixture(tmp_path, history=True)['items']
    assert row['input_id'] is None
    assert row['tool_relations'] == []


def test_duplicate_id_is_ambiguous(tmp_path):
    row, = fixture(tmp_path, duplicate=True)['items']
    assert row['input_id'] is None
    assert row['association_status'] == 'ambiguous'


def test_case_isolation(tmp_path):
    row, = fixture(tmp_path, wrong_case=True)['items']
    assert row['input_id'] is None
    assert row['tool_relations'][0]['status'] == 'unobserved'


def test_replayed_response_is_ambiguous(tmp_path):
    assert all(row['association_status'] == 'ambiguous' for row in fixture(tmp_path, repeated_response=True)['items'])


def test_stream_protocols_and_arguments():
    assert emitted_tool_ids({'events': [
        {'type': 'content_block_start', 'content_block': {'type': 'tool_use', 'id': 'anthropic'}},
        {'choices': [{'delta': {'tool_calls': [{'id': 'chat'}]}}]},
        {'type': 'response.output_item.added', 'item': {'type': 'function_call', 'call_id': 'responses'}},
    ], 'input': {'type': 'tool_use', 'id': 'forged'}}) == {'anthropic', 'chat', 'responses'}


def test_optional_execution_scope_keeps_unknown_candidates_and_legacy_default():
    from agentbench.observe.tool_links import resolve_tools, SCOPE_KEYS
    models = [{"id": "a", "execution_id": "child-a", "emitted_tool_ids": ["same"]},
              {"id": "b", "execution_id": "child-b", "emitted_tool_ids": ["same"]}]
    tools = [{"id": "ta", "execution_id": "child-a", "tool_call_id": "same"},
             {"id": "tb", "execution_id": "child-b", "tool_call_id": "same"}]
    assert all(v[0]["status"] == "ambiguous" for v in resolve_tools(models, tools).values())
    scoped = (*SCOPE_KEYS, "execution_id")
    assert all(v[0]["status"] == "exact" for v in resolve_tools(models, tools, scope_keys=scoped).values())
    tools.append({"id": "unknown", "tool_call_id": "same"})
    assert all(v[0]["status"] == "ambiguous" for v in resolve_tools(models, tools, scope_keys=scoped).values())

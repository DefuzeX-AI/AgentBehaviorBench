"""Exact tool call associations from recorded framework span IDs."""
import json
from agentbench.observe.interactions import load_index
from agentbench.trajectory import build, validate
from tests.trajectory_fixtures import langgraph_attempt


def _framework(root):
    path = root / 'steps/0001/framework.jsonl'
    return path, [json.loads(line) for line in path.read_text().splitlines()]


def _write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_tool_call_ids_recorded_only_at_end_are_exactly_linked(tmp_path):
    root = langgraph_attempt(tmp_path)
    path, rows = _framework(root)
    for row in rows:
        if row['event'] == 'span_start' and row['data'].get('kind') == 'tool':
            row['data'].pop('tool_call_id', None)
    _write_rows(path, rows)
    value = validate(build(root))
    assert [(log['tool_call_id'], log['link']) for log in value['steps'][0]['tool_logs']] == [
        ('call_ls', 'exact'), ('call_cat', 'exact')]
    assert value['coverage']['unlinked_tool_calls'] == 0


def test_conflicting_start_end_ids_are_never_linked(tmp_path):
    root = langgraph_attempt(tmp_path)
    path, rows = _framework(root)
    for row in rows:
        if row['event'] == 'span_start' and row['data'].get('span_id') == 'tool-ls':
            row['data']['tool_call_id'] = 'contradictory-id'
    _write_rows(path, rows)
    index = load_index(root)
    row = next(row for row in index.rows if row.get('framework_span_id') == 'tool-ls')
    assert row['tool_call_id'] is None
    assert any('tool call ID' in w and 'conflict' in w.lower() for w in index.warnings)
    value = validate(build(root))
    log = value['steps'][0]['tool_logs'][0]
    assert log['link'] == 'none' and log['execution_status'] == 'not_observed'


def test_reused_emitted_id_is_ambiguous_not_exact(tmp_path):
    root = langgraph_attempt(tmp_path)
    path = root / 'logs/network.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    first = next(row for row in rows if row['event'] == 'llm_response' and row['data']['call_id'] == 'call-1')
    second = next(row for row in rows if row['event'] == 'llm_response' and row['data']['call_id'] == 'call-2')
    second['data']['payload'] = first['data']['payload']
    _write_rows(path, rows)
    value = validate(build(root))
    models = [s for s in value['steps'] if s['kind'] == 'model']
    assert all(log['link'] == 'ambiguous' for step in models for log in step['tool_logs'])
    assert all(log['outputs'] is None for step in models for log in step['tool_logs'])
    assert value['coverage']['ambiguous_links'] == 4
    assert len([s for s in value['steps'] if s['kind'] == 'tool_only']) == 2
    assert value['status'] == 'partial'


def test_tool_argument_ids_are_not_used_as_identity(tmp_path):
    root = langgraph_attempt(tmp_path)
    path, rows = _framework(root)
    for row in rows:
        if row['event'] in ('span_start', 'span_end') and row['data'].get('span_id') in ('tool-ls', 'tool-cat'):
            row['data'].pop('tool_call_id', None)
            if row['event'] == 'span_start':
                row['data']['input'] = {'tool_call_id': 'call_ls'}
    _write_rows(path, rows)
    value = validate(build(root))
    assert all(log['link'] == 'none' for log in value['steps'][0]['tool_logs'])
    assert value['coverage']['unlinked_tool_calls'] == 2

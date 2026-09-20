"""Network identity survives missing Input links; payload text is not identity."""
import json

from agentbench.observe.interactions import interactions


def write_run(root, *, payload=None, explicit_input=None):
    folder = root / 'evaluation/inputs/0001'
    folder.mkdir(parents=True)
    (folder / 'input.json').write_text(json.dumps({'case_id': 'case-1', 'input_id': 'step-1', 'payload': 'hello'}))
    data = {'call_id': 'request-1', 'case_id': 'case-1', 'attempt_id': 'attempt-1',
            'host': 'model.example', 'payload': payload or {}}
    if explicit_input:
        data['input_id'] = explicit_input
    rows = [{'event': 'llm_request', 'source': 'interceptor', 'data': data},
            {'event': 'llm_response', 'source': 'interceptor',
             'data': {'call_id': 'request-1', 'case_id': 'case-1', 'status': 200}}]
    (root / 'network.jsonl').write_text('\n'.join(json.dumps(row) for row in rows))


def test_case_identity_and_unassigned_requests_survive_input_filter(tmp_path):
    write_run(tmp_path)
    all_rows = interactions(tmp_path, {'kinds': 'chat'})
    row, = all_rows['items']
    assert row['case_id'] == 'case-1'
    assert row['input_id'] is None
    assert row['association_status'] == 'case_only'
    assert row['attempt_id'] == 'attempt-1'
    filtered = interactions(tmp_path, {'kinds': 'chat', 'input_id': 'step-1'})
    assert filtered['total'] == 0
    assert filtered['unassigned_request_count'] == 1
    missing = interactions(tmp_path, {'kinds': 'chat', 'input_id': 'step-1', 'input_scope': 'unassigned'})
    assert [item['id'] for item in missing['items']] == [row['id']]


def test_payload_cannot_claim_a_case_or_input(tmp_path):
    write_run(tmp_path, payload={'input_id': 'step-1', 'case_id': 'case-1'})
    row, = interactions(tmp_path, {'kinds': 'chat'})['items']
    assert row['input_id'] is None
    assert row['link_evidence'] is None


def test_explicit_record_identity_can_link_input(tmp_path):
    write_run(tmp_path, explicit_input='step-1')
    row, = interactions(tmp_path, {'kinds': 'chat'})['items']
    assert row['input_id'] == 'step-1'
    assert row['association_status'] == 'input_exact'
    assert row['link_evidence'] == 'record_input_id'


def test_title_purpose_preserves_session_only_ownership(tmp_path):
    write_run(tmp_path)
    path = tmp_path / 'network.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['data'].update(native_session_id='native-1', native_purpose='session_title',
                           purpose_evidence='declared_tool_set')
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    result = interactions(tmp_path, {'kinds': 'chat'})
    row, = result['items']
    assert row['purpose'] == 'session_title'
    assert row['purpose_evidence'] == 'declared_tool_set'
    assert row['association_status'] == 'session_only'
    assert row['input_id'] is None

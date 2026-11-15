import copy
import json

from agentbench.observe.interactions import load_index
from agentbench.trajectory.builder import build
from tests.trajectory_fixtures import acp_attempt, write_json, write_jsonl


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def relation(root):
    return next(row for row in load_index(root).rows if row['kind'] == 'chat')['tool_relations'][0]


def test_missing_input_case_uses_recorded_invocation_context(tmp_path):
    root = acp_attempt(tmp_path)
    path = root / 'steps/0001/input.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value.pop('case_id')
    write_json(path, value)
    assert relation(root)['status'] == 'exact'
    assert build(root)['steps'][0]['tool_logs'][0]['link'] == 'exact'


def test_conflicting_case_never_links(tmp_path):
    root = acp_attempt(tmp_path)
    path = root / 'logs/network.jsonl'
    wire = rows(path)
    for row in wire:
        row['data']['case_id'] = 'different-case'
    write_jsonl(path, wire)
    assert relation(root)['status'] != 'exact'
    assert build(root)['steps'][0]['tool_logs'][0]['link'] != 'exact'


def test_reused_tool_id_does_not_attribute_execution_twice(tmp_path):
    root = acp_attempt(tmp_path)
    path = root / 'logs/network.jsonl'
    wire = rows(path)
    duplicate = copy.deepcopy(wire)
    for row in duplicate:
        row['data']['call_id'] = 'another-request'
    write_jsonl(path, wire + duplicate)
    assert relation(root)['status'] == 'ambiguous'
    value = build(root)
    models = [step for step in value['steps'] if step['kind'] == 'model']
    assert all(step['tool_logs'][0]['link'] == 'ambiguous' for step in models)
    assert any(step['kind'] == 'tool_only' and step['tool_logs'][0]['tool_call_id'] == 'call_sh'
               for step in value['steps'])


def test_ambiguous_candidates_retain_every_execution_output(tmp_path):
    root = acp_attempt(tmp_path)
    path = root / 'steps/0001/framework.jsonl'
    events = rows(path)
    duplicate = copy.deepcopy(events[:3])
    for row in duplicate:
        row['data']['span_id'] = 'acp:second'
    duplicate[-1]['data']['output'] = 'SECOND_TOOL_OUTPUT'
    write_jsonl(path, events + duplicate)
    value = build(root)
    assert value['steps'][0]['tool_logs'][0]['link'] == 'ambiguous'
    assert 'SECOND_TOOL_OUTPUT' in json.dumps(value)

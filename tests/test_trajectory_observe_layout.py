"""Read the actual one-shot layout without moving files or inventing Input IDs."""
import json

import pytest

from agentbench.observe.interactions import load_index
from agentbench.trajectory import build, validate
from tests.trajectory_fixtures import langgraph_attempt, write_json, write_jsonl


def observe_attempt(root, name='invocation-one', prompt='你好，España'):
    langgraph_attempt(root)
    source = root / 'steps/0001'
    destination = root / name / 'output'
    destination.parent.mkdir(exist_ok=True)
    source.rename(destination)
    (root / 'steps').rmdir()
    (root / 'case.json').unlink()
    (destination / 'input.json').unlink()
    (destination / 'request.json').unlink()
    write_json(root / 'run.json', {'schema': 'abb.observe.run.v1', 'run_id': 'run',
                                  'agent_id': 'alpha', 'status': 'succeeded', 'input': prompt})
    write_json(root / name / 'input/request.json', {
        'schema': 'abb.invocation.v1', 'run_id': name, 'session_id': 'run',
        'agent_id': 'alpha', 'framework': 'langgraph', 'input': prompt, 'config': None})
    for path in (destination / 'framework.jsonl', root / 'logs/network.jsonl'):
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for row in rows:
            data = row['data']
            data.pop('case_id', None)
            data.pop('input_id', None)
            if path.name == 'framework.jsonl':
                data['invocation_id'] = name
            for key in ('span_id', 'parent_span_id', 'framework_span_id', 'call_id'):
                if data.get(key):
                    data[key] = name + ':' + data[key]
        write_jsonl(path, rows)
    return root


@pytest.mark.parametrize('prompt', ['你好，España', {'message': '你好', 'items': [1, 2]}, ''])
def test_observe_reads_request_input_and_framework_without_fabricating_ids(tmp_path, prompt):
    root = observe_attempt(tmp_path, prompt=prompt)
    value = validate(build(root))
    assert value['framework'] == 'langgraph'
    assert value['inputs'][0]['prompt'] == prompt
    assert value['metadata']['task_instruction'] == prompt
    assert value['inputs'][0]['input_id'] is None
    assert value['case_id'] is None
    assert value['status'] == 'complete'
    assert value['inputs'][0]['ordinal'] == 'invocation-one'
    assert all(s['input_ordinal'] == 'invocation-one' for s in value['steps'])
    assert all(log['link'] == 'exact' for s in value['steps'] for log in s['tool_logs'])
    assert 'invocation-one/input/request.json' in {s['path'] for s in value['sources']}
    assert not (root / 'invocation-one/output/input.json').exists()
    assert not (root / 'invocation-one/output/request.json').exists()


def test_multiple_invocations_keep_distinct_inputs_and_reused_tool_ids(tmp_path):
    root = observe_attempt(tmp_path / 'run', 'invocation-one', 'first')
    other = observe_attempt(tmp_path / 'other', 'invocation-two', 'second')
    (other / 'invocation-two').rename(root / 'invocation-two')
    wire = root / 'logs/network.jsonl'
    wire.write_bytes(wire.read_bytes() + (other / 'logs/network.jsonl').read_bytes())
    value = validate(build(root))
    assert [(i['ordinal'], i['prompt']) for i in value['inputs']] == [
        ('invocation-one', 'first'), ('invocation-two', 'second')]
    assert {s['input_ordinal'] for s in value['steps']} == {'invocation-one', 'invocation-two'}
    assert len(value['steps']) == 4
    assert all(log['link'] == 'exact' for s in value['steps'] for log in s['tool_logs'])
    assert value['coverage']['unlinked_tool_calls'] == 0


def test_missing_observe_request_remains_missing_evidence(tmp_path):
    root = observe_attempt(tmp_path)
    (root / 'invocation-one/input/request.json').unlink()
    value = validate(build(root))
    assert value['inputs'][0]['prompt'] is None
    assert value['framework'] == 'unknown'
    assert value['status'] == 'partial'


def test_recorded_input_is_authoritative_when_also_present(tmp_path):
    root = observe_attempt(tmp_path, prompt='mapped payload')
    write_json(root / 'invocation-one/output/input.json', {'input_id': 'recorded-input', 'payload': 'original prompt'})
    value = validate(build(root))
    assert value['inputs'][0]['prompt'] == 'original prompt'
    assert value['inputs'][0]['input_id'] == 'recorded-input'


def test_invocation_identity_conflicts_are_not_silently_reassigned(tmp_path):
    root = observe_attempt(tmp_path)
    path = root / 'invocation-one/input/request.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['run_id'] = 'different-invocation'
    write_json(path, value)
    index = load_index(root)
    assert any('invocation_id' in row.get('identity_conflicts', []) for row in index.rows)
    value = validate(build(root))
    assert value['status'] == 'partial'
    assert all(log['link'] != 'exact' for s in value['steps'] for log in s['tool_logs'])


def test_request_symlinks_cannot_escape_the_run(tmp_path):
    root = observe_attempt(tmp_path / 'run')
    path = root / 'invocation-one/input/request.json'
    path.rename(tmp_path / 'outside.json')
    path.symlink_to(tmp_path / 'outside.json')
    with pytest.raises(ValueError, match='Artifact reference leaves its root|Linked artifact'):
        build(root)

"""trajectory.json is derived from recorded identifiers and keeps every step whole."""
import json

import pytest

from agentbench.trajectory import build, read, validate, write
from tests.trajectory_fixtures import acp_attempt, langgraph_attempt, PROMPT


def test_langgraph_model_calls_become_steps_with_linked_tool_logs(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    assert value['status'] == 'complete' and value['framework'] == 'langgraph'
    assert [s['kind'] for s in value['steps']] == ['model', 'model']
    assert [s['step_id'] for s in value['steps']] == [1, 2]
    first, second = value['steps']
    assert first['agent_name'] == 'alpha' and first['source'] == 'wire+framework'
    # The model saw the complete provider request, not a summary of it.
    assert first['input']['messages'][0]['content'] == 'You are alpha.'
    assert first['input']['parameters'] == {'temperature': 0}
    assert [c['name'] for c in first['output']['tool_calls']] == ['ls', 'cat']
    assert [(l['tool_name'], l['execution_status'], l['link'], l['outputs']) for l in first['tool_logs']] == [
        ('ls', 'succeeded', 'exact', 'a.txt'), ('cat', 'succeeded', 'exact', 'hello')]
    assert second['output']['text'] == 'The file says hello.' and second['tool_logs'] == []
    assert second['output']['usage'] == {'prompt_tokens': 20, 'completion_tokens': 4}
    assert value['inputs'][0]['step_range'] == [1, 2] and value['inputs'][0]['prompt'] == PROMPT
    assert value['coverage']['model_calls'] == 'wire+framework'
    assert value['coverage']['tool_calls'] == 'framework'
    assert value['coverage']['unlinked_tool_calls'] == 0
    assert value['metadata']['task_instruction'] == PROMPT
    assert value['metadata']['agent_configuration']['system_prompt'] == 'You are alpha.'
    assert [t['function']['name'] for t in value['metadata']['agent_configuration']['tools']] == ['ls', 'cat']
    assert {s['path'] for s in value['sources']} >= {'logs/network.jsonl', 'steps/0001/framework.jsonl'}


def test_historical_layout_yields_the_same_steps(tmp_path):
    current = validate(build(langgraph_attempt(tmp_path / 'new', layout='steps')))
    historical = validate(build(langgraph_attempt(tmp_path / 'old', layout='evaluation/inputs')))
    def strip(value):
        return [{k: ([{lk: lv for lk, lv in log.items() if lk != 'evidence'} for log in v] if k == 'tool_logs' else v)
                 for k, v in s.items() if k != 'evidence'} for s in value['steps']]
    assert strip(historical) == strip(current)
    assert historical['inputs'][0]['ordinal'] == '0001'
    assert {s['path'] for s in historical['sources']} == {s['path'] for s in current['sources']}


def test_wire_failure_falls_back_to_framework_output_and_graph_node_tool_calls(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path, drop_wire_response=True)))
    first = value['steps'][0]
    assert first['output_source'] == 'framework'
    assert first['output']['wire_error']['error_code'] == 'transport_error'
    assert first['output']['tool_calls_source'] == 'graph_node'
    assert [l['link'] for l in first['tool_logs']] == ['exact', 'exact']
    assert value['coverage']['unlinked_tool_calls'] == 0


def test_acp_wire_calls_link_terminal_tools_and_keep_direct_tools_as_steps(tmp_path):
    value = validate(build(acp_attempt(tmp_path)))
    assert value['framework'] == 'acp' and value['coverage']['tool_calls'] == 'acp'
    assert [s['kind'] for s in value['steps']] == ['model', 'tool_only']
    model, direct = value['steps']
    assert model['output']['reasoning'] == 'think'
    assert model['output']['tool_calls'] == [{'id': 'call_sh', 'name': 'exec', 'arguments': {'command': 'exit 3'}}]
    log = model['tool_logs'][0]
    assert log['link'] == 'exact' and log['input_arguments'] == {'command': 'exit 3'}
    assert log['exit_status'] == {'exitCode': 3, 'signal': None}
    assert direct['tool_logs'][0]['tool_name'] == 'read' and direct['tool_logs'][0]['link'] == 'none'
    assert value['coverage']['unlinked_tool_calls'] == 1


def test_unobserved_tool_execution_is_reported_not_invented(tmp_path):
    root = acp_attempt(tmp_path)
    (root / 'steps/0001/framework.jsonl').write_text('', encoding='utf-8')
    value = validate(build(root))
    assert value['status'] == 'partial'
    assert value['steps'][0]['tool_logs'][0]['execution_status'] == 'not_observed'
    assert any('not observed' in w for w in value['warnings'])


def test_oversized_values_are_marked_not_silently_cut(tmp_path):
    root = langgraph_attempt(tmp_path)
    value = validate(build(root, environ={'ABB_TRAJECTORY_MAX_VALUE_BYTES': str(64 * 1024)}))
    assert value['steps'][0]['input']['messages'][0]['content'] == 'You are alpha.'
    big = 'x' * (70 * 1024)
    (root / 'steps/0001/result.json').write_text(json.dumps({'status': 'succeeded', 'output': big}), encoding='utf-8')
    value = validate(build(root, environ={'ABB_TRAJECTORY_MAX_VALUE_BYTES': str(64 * 1024)}))
    marker = value['inputs'][0]['result']['output']
    assert marker['truncated'] is True and marker['size'] == len(big) and len(marker['head']) == 64 * 1024


def test_write_always_leaves_a_validated_file(tmp_path):
    root = langgraph_attempt(tmp_path)
    status = write(root)
    assert status['status'] == 'complete' and status['steps'] == 2
    assert read(root)['steps'][1]['output']['text'] == 'The file says hello.'
    (root / 'run.json').write_text('{"run_id": "broken", "agent_id": "alpha"}', encoding='utf-8')
    (root / 'steps').rename(root / 'gone')
    status = write(root)
    assert status['status'] in ('partial', 'failed')
    assert read(root)['status'] == status['status']


def test_trajectory_is_self_contained(tmp_path):
    root = langgraph_attempt(tmp_path / 'attempt')
    write(root)
    alone = tmp_path / 'alone'
    alone.mkdir()
    (alone / 'trajectory.json').write_bytes((root / 'trajectory.json').read_bytes())
    value = read(alone)
    assert value['steps'][0]['input']['messages'] and value['steps'][0]['tool_logs'][1]['outputs'] == 'hello'


def test_cli_build_prints_then_writes_and_refuses_silent_replacement(tmp_path, capsys):
    from types import SimpleNamespace
    from agentbench.cli.features.trajectory import execute
    root = langgraph_attempt(tmp_path)
    assert execute(SimpleNamespace(trajectory_command='build', directory=root, write=False, force=False)) == 0
    assert json.loads(capsys.readouterr().out)['steps'][0]['step_id'] == 1
    assert not (root / 'trajectory.json').exists()
    assert execute(SimpleNamespace(trajectory_command='build', directory=root, write=True, force=False)) == 0
    saved = read(root)
    (root / 'trajectory.json').write_text(json.dumps({**saved, 'warnings': ['edited by hand']}), encoding='utf-8')
    assert execute(SimpleNamespace(trajectory_command='build', directory=root, write=True, force=False)) == 1
    assert 'use --force' in capsys.readouterr().err
    assert read(root)['warnings'] == ['edited by hand']
    assert execute(SimpleNamespace(trajectory_command='build', directory=root, write=True, force=True)) == 0
    assert read(root)['warnings'] == []
    assert execute(SimpleNamespace(trajectory_command='show', directory=root, mode='response_only')) == 0
    assert 'Step 1 - alpha [model]' in capsys.readouterr().out


@pytest.mark.parametrize('mutate, message', [
    (lambda v: v.update(schema='other'), 'unknown schema'),
    (lambda v: v['steps'][0].update(step_id=5), 'step_id'),
    (lambda v: v['steps'][0].update(input_ordinal='9999'), 'unknown input'),
    (lambda v: v['steps'][0]['tool_logs'][0].update(link='guess'), 'unknown link'),
])
def test_validation_rejects_broken_contracts(tmp_path, mutate, message):
    value = build(langgraph_attempt(tmp_path))
    mutate(value)
    with pytest.raises(ValueError, match=message):
        validate(value)

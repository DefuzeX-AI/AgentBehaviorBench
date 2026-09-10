"""Contract regression tests for independent container evaluator integration."""
import json
from dataclasses import asdict
import pytest
from agentbench.sdk.plugins import resolve_sdk, plugin_execution
from agentbench.sdk.panda.benchmark import read_result


def test_container_selection_and_legacy_aliases():
    assert plugin_execution(resolve_sdk('panda').value) == 'container'
    from agentbench.sdk.kuma_runtime import benchmark as old
    from agentbench.sdk.kuma import benchmark as new
    assert old is new
    from agentbench.evaluation.input_binding import InputBinding as old_binding
    from agentbench.sdk.common.input_binding import InputBinding
    assert old_binding is InputBinding


@pytest.fixture
def artifacts(tmp_path):
    data = {
        'manifest.json': {'phase': 'finished', 'execution': 'succeeded', 'judge': 'received',
            'agent_id': 'agent', 'run_id': 'run', 'case_id': 'case',
            'steps': [{'input_id': 'input', 'directory': 'inputs/0001'}]},
        'case.json': {'case_id': 'case', 'inputs': [{'input_id': 'input', 'payload': 'hello'}]},
        'judge/report.json': {'status': 'pass', 'confidence': 1.0, 'issues': [],
            'evidence_gaps': [], 'run_id': 'run', 'case_id': 'case'},
        'inputs/0001/input.json': {'input_id': 'input', 'payload': 'hello'},
        'inputs/0001/request.json': {'agent_id': 'agent', 'run_id': 'invoke', 'session_id': 'run'},
        'inputs/0001/result.json': {'agent_id': 'agent', 'run_id': 'invoke', 'status': 'succeeded', 'output': 'hello'},
        'inputs/0001/submission.json': {'input_id': 'input', 'status': 'completed', 'output': 'hello'},
    }
    for name, value in data.items():
        path = tmp_path / 'evaluation' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    return tmp_path


def test_report_is_structured_and_validated(artifacts):
    result = read_result(artifacts, 'agent')
    assert result.passed and result.history_count == 1
    assert asdict(result)['report']['status'] == 'pass'


def test_reject_mismatched_agent_submission(artifacts):
    path = artifacts / 'evaluation/inputs/0001/submission.json'
    value = json.loads(path.read_text())
    value['output'] = 'tampered'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='submission identity'):
        read_result(artifacts, 'agent')

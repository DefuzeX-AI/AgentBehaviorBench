"""Exp3 repeats one frozen submission, retaining failures and unknown evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from agentbench.experiments.exp3 import Experiment3
from agentbench.harness.ground_truth.repair import (
    summarize, trial_verdict, EXPECTED_SYSTEM, expected_payload, defect_payload, validate_expected_observation)
from agentbench.harness.ground_truth.repair_requirements import (
    SYSTEM as REQUIREMENTS_SYSTEM, prepare_requirements)
from tests.test_exp1 import install_issue, answer, prepared, project, oracle
from tests.test_sdk_defaults import inprocess_worker_permissions


def requirements():
    return {'requirements': [{'id': 'r1', 'description': 'Echo the input.', 'evidence_kind': 'model_response'}]}


@pytest.fixture
def repair_project(prepared, monkeypatch, tmp_path, tmp_path_factory):
    f = prepared
    f.results = tmp_path_factory.mktemp('e3')
    definition = f.folder / 'verify.case.json'
    document = json.loads(definition.read_text(encoding='utf-8'))
    document['steps'] = ['hello']
    definition.write_text(json.dumps(document), encoding='utf-8')
    source = tmp_path / 'source'
    shutil.copytree(f.target.registration.path / 'agent', source)
    (source / 'marker.txt').write_text('submitted version', encoding='utf-8')
    model = SimpleNamespace(model='fixture', base_url='https://example.test')
    monkeypatch.setattr('agentbench.experiments.exp3.oracle_model', lambda _: model)
    # Keep the real Suite/evidence/identity checks, then provide the explicitly
    # synthetic trace fixture to isolate oracle orchestration from model calls.
    original = f.service.evidence
    def evidence(*args):
        value = original(*args)
        return {**value, 'trajectory': deepcopy(f.candidate)}
    monkeypatch.setattr(f.service, 'evidence', evidence)
    return f, source


def test_three_runs_use_one_snapshot_and_same_case(repair_project, monkeypatch, tmp_path):
    f, source = repair_project
    calls = []
    original = f.service.execute
    def execute(agent_id, cases, **kwargs):
        target = kwargs['target']
        calls.append((deepcopy(cases), target, kwargs))
        if len(calls) > 1:
            assert (target.registration.path / 'agent/marker.txt').read_text(encoding='utf-8') == 'submitted version'
        (source / 'marker.txt').write_text('edited during run', encoding='utf-8')
        return original(agent_id, cases, **kwargs)
    monkeypatch.setattr(f.service, 'execute', execute)
    defect_count = 0
    def ask(model, *, system, payload):
        nonlocal defect_count
        if system == REQUIREMENTS_SYSTEM:
            assert not calls  # Requirements are frozen before either execution.
            assert set(payload) == {'expected', 'case'}
            return requirements()
        if system == EXPECTED_SYSTEM:
            assert 'reference_trajectories' not in payload
            assert set(payload['issue']) == {'expected', 'requirements'}
            return {**answer(True), 'reference_step_ids': [], 'witnesses': [
                {'requirement_id': 'r1', 'step_id': 2, 'observation': 'The file says hello.'}]}
        defect_count += 1
        return answer(defect_count == 1)
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask, output=lambda _: None).run(
        'example', issue=1, source=source, results_dir=f.results)
    assert result['verdict'] == 'PASS'
    assert result['scope'] == 'original_reproduction_case'
    assert result['completed_runs'] == 3 and len(calls) == 4
    assert len({row['suite'] for row in result['trials']}) == 3
    assert len({str(call[1].registration.path) for call in calls[1:]}) == 1
    assert all(call[0] == calls[0][0] for call in calls)
    assert all(call[2]['retry_policy'].max_retries == 0 for call in calls)
    assert all(row['expected_met'] is True for row in result['trials'])
    assert f.target.registration.path != Path(result['candidate_target']['path'])
    f.target.validate()


def test_failure_does_not_stop_remaining_runs(repair_project, tmp_path):
    f, source = repair_project
    result = Experiment3(f.service.root, execution_service=f.service,
        ask=lambda *a, **k: answer(True), output=lambda _: None).run(
        'example', issue=1, source=source, runs=2, results_dir=f.results)
    assert result['verdict'] == 'FAIL'
    assert result['completed_runs'] == result['failure_reproduced_runs'] == 2


def test_absent_defect_without_expected_evidence_is_unknown(repair_project, tmp_path):
    f, source = repair_project
    calls = 0
    def ask(model, *, system, payload):
        nonlocal calls
        if system == REQUIREMENTS_SYSTEM:
            return requirements()
        if system == EXPECTED_SYSTEM:
            return {'match': None, 'reason': 'Required output missing', 'reference_step_ids': [],
                    'candidate_step_ids': [], 'candidate_decisive_step': None}
        calls += 1
        return answer(calls == 1)
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask, output=lambda _: None).run(
        'example', issue=1, source=source, runs=1, results_dir=f.results)
    assert result['verdict'] == 'UNKNOWN'
    assert result['trials'][0]['hit'] is False
    assert result['trials'][0]['expected_met'] is None


def test_transport_failures_stay_unknown_and_all_runs_are_attempted(repair_project, tmp_path):
    f, source = repair_project
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError('Provider unavailable')
    result = Experiment3(f.service.root, execution_service=f.service, ask=unavailable, output=lambda _: None).run(
        'example', issue=1, source=source, results_dir=f.results)
    assert result['verdict'] == 'UNKNOWN' and result['completed_runs'] == 3
    assert all(row['state'] == 'failed' for row in result['trials'])
    assert len(calls) == 5  # One requirements call, one baseline, three candidate oracles.


def test_expected_context_never_contains_reference_actions(repair_project):
    f, _ = repair_project
    reference = {'definition': {'expected': 'Required outcome', 'defect': 'secret old failure'},
                 'trajectories': [{**f.candidate, 'attempt': 'reference'}]}
    for full in (False, True):
        value = expected_payload(reference, f.candidate, full_context=full)
        assert 'reference_trajectories' not in value
        assert value['issue'] == {'expected': 'Required outcome'}
        defect = defect_payload(reference, f.candidate, full_context=full)
        assert defect['issue'] == {'defect': 'secret old failure'}
        assert defect['reference_trajectories']


def test_expected_tool_claim_requires_real_result_and_required_arguments():
    plan = {'requirements': [{'id': 'r1', 'description': 'Read the required file.',
                             'evidence_kind': 'tool_result', 'tool_name': 'read',
                             'required_tool_arguments': {'path': 'original'}}]}
    candidate = {'steps': [{'step_id': 1, 'output': {'text': 'Summary claims a tool succeeded'},
                            'tool_logs': []}, {'step_id': 2, 'output': {}, 'tool_logs': [
        {'tool_name': 'read', 'input_arguments': {'path': 'changed'}, 'outputs': 'Actual result'}]}]}
    witness = {'requirement_id': 'r1', 'step_id': 1, 'tool_log_index': 0, 'observation': 'Actual result'}
    reply = {'match': True, 'candidate_decisive_step': 1, 'candidate_step_ids': [1, 2],
             'candidate_observation': 'Actual result', 'witnesses': [witness]}
    with pytest.raises(ValueError, match='actual tool log'):
        validate_expected_observation(reply, candidate, plan)
    # The judge cannot change the frozen source kind to make a model claim pass.
    witness['evidence_kind'] = 'model_response'
    with pytest.raises(ValueError, match='actual tool log'):
        validate_expected_observation(reply, candidate, plan)
    reply['candidate_decisive_step'] = 2
    witness['step_id'] = 2
    with pytest.raises(ValueError, match='arguments differ'):
        validate_expected_observation(reply, candidate, plan)
    # Even supplying weaker constraints in the verdict cannot change the plan.
    witness['required_tool_arguments'] = {}
    with pytest.raises(ValueError, match='arguments differ'):
        validate_expected_observation(reply, candidate, plan)
    candidate['steps'][1]['tool_logs'][0]['input_arguments']['path'] = 'original'
    validate_expected_observation(reply, candidate, plan)
    witness['observation'] = 'Summary claims a tool succeeded'
    with pytest.raises(ValueError, match='absent'):
        validate_expected_observation(reply, candidate, plan)
    reply['witnesses'] = []
    with pytest.raises(ValueError, match='every frozen requirement'):
        validate_expected_observation(reply, candidate, plan)


def test_requirements_failure_retains_reply_without_executions(tmp_path):
    model = SimpleNamespace(model='fixture', base_url='https://example.test')
    with pytest.raises(ValueError, match='unavailable'):
        prepare_requirements('Needs evidence not in a model reply', {'inputs': []},
            directory=tmp_path, environ={}, model=model,
            ask=lambda *a, **k: {'requirements': None, 'reason': 'Unsupported observation'})
    record = json.loads((tmp_path / 'requirements-call.json').read_text(encoding='utf-8'))
    assert record['state'] == 'failed'
    assert record['reply']['reason'] == 'Unsupported observation'


def test_model_claim_cannot_pass_a_frozen_tool_requirement(repair_project):
    f, source = repair_project
    defects, expected_calls = 0, 0
    def ask(model, *, system, payload):
        nonlocal defects, expected_calls
        if system == REQUIREMENTS_SYSTEM:
            return {'requirements': [{'id': 'r1', 'description': 'Read the specified path.',
                'evidence_kind': 'tool_result', 'tool_name': 'read',
                'required_tool_arguments': {'path': 'required.txt'}}]}
        if system.startswith(EXPECTED_SYSTEM):
            expected_calls += 1
            # The synthetic trajectory contains this response, but no tool call.
            return {**answer(True), 'reference_step_ids': [], 'witnesses': [
                {'requirement_id': 'r1', 'step_id': 2, 'tool_log_index': 0,
                 'observation': 'The file says hello.'}]}
        defects += 1
        return answer(defects == 1)
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask,
        output=lambda _: None).run('example', issue=1, source=source, runs=1, results_dir=f.results)
    assert result['verdict'] == 'UNKNOWN'
    assert expected_calls == 2  # One bounded correction, then retain invalid evidence.
    trial = result['trials'][0]
    assert trial['hit'] is False and trial['expected_met'] is None
    assert 'actual tool log' in trial['reason']
    assert any((Path(result['directory']) / 'trials/0001/oracle/expected').rglob('*.json'))


def test_score_requires_confirmed_baseline_and_full_budget():
    passed = {'verdict': 'PASS'}
    assert summarize({'hit': False}, [passed] * 3, 3) == 'UNKNOWN'
    assert summarize({'hit': True}, [passed] * 2, 3) == 'UNKNOWN'
    assert summarize({'hit': True}, [passed] * 3, 3) == 'PASS'
    assert summarize({'hit': None}, [passed, {'verdict': 'FAIL'}], 3) == 'FAIL'
    assert trial_verdict(False, False) == 'FAIL'
    assert trial_verdict(False, None) == 'UNKNOWN'


def test_cli_default_runs_and_saved_result(tmp_path, capsys):
    from agentbench.cli.main import build_parser, cli
    args = build_parser().parse_args(['exp3', 'run', 'example', '--issue', '1', '--source', str(tmp_path)])
    assert args.runs == 3
    (tmp_path / 'result.json').write_text(json.dumps({'schema': 'abb.exp3.v1', 'verdict': 'UNKNOWN'}), encoding='utf-8')
    assert cli(['exp3', 'result', '--experiment', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['verdict'] == 'UNKNOWN'

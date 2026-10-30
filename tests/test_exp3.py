"""Exp3 repeats one frozen submission, retaining failures and unknown evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from agentbench.experiments.exp3 import Experiment3
from agentbench.experiments.exp3_judging import RepairJudging
from agentbench.harness.ground_truth.repair import (
    summarize, REPAIR_SYSTEM, adapt_repair_reply, repair_trial_verdict)
from tests.test_exp1 import install_issue, answer, prepared, project, oracle
from tests.test_sdk_defaults import inprocess_worker_permissions


def repair_answer(label):
    return {'label': label, 'reason': 'Observed candidate execution evidence.',
            'reference_step_ids': ['runs/run-01/trajectory/reference/1'] if label == 'bug_exist' else [],
            'candidate_step_ids': [2] if label != 'unknown' else [],
            'candidate_decisive_step': 2 if label != 'unknown' else None,
            'candidate_observation': 'The file says hello.' if label != 'unknown' else None}


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
    monkeypatch.setattr('agentbench.experiments.exp3_judging.oracle_model', lambda _: model)
    # Keep the real Suite/evidence/identity checks, then provide the explicitly
    # synthetic trace fixture to isolate oracle orchestration from model calls.
    original = f.service.evidence
    def evidence(*args):
        value = original(*args)
        candidate = deepcopy(f.candidate)
        candidate['case_id'] = value['trajectory']['case_id']
        return {**value, 'trajectory': candidate}
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
        assert system == REPAIR_SYSTEM
        assert set(payload['issue']) == {'defect', 'Root cause', 'expected'}
        assert payload['reference_trajectories']
        defect_count += 1
        return repair_answer('bug_exist' if defect_count == 1 else 'bug_fixed')
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask, output=lambda _: None).run(
        'example', issue=1, source=source, results_dir=f.results)
    assert result['verdict'] == 'NOT_JUDGED'
    assert defect_count == 0
    judged = RepairJudging(result['directory']).auto(environ={}, ask=ask)
    assert judged['verdict'] == 'PASS'
    assert result['scope'] == 'original_reproduction_case'
    assert result['completed_runs'] == 3 and len(calls) == 4
    assert len({row['suite'] for row in result['trials']}) == 3
    assert len({str(call[1].registration.path) for call in calls[1:]}) == 1
    assert all(call[0] == calls[0][0] for call in calls)
    assert all(call[2]['retry_policy'].max_retries == 0 for call in calls)
    assert all(row['label'] is None for row in result['trials'])
    assert f.target.registration.path != Path(result['candidate_target']['path'])
    f.target.validate()


def test_failure_does_not_stop_remaining_runs(repair_project, tmp_path):
    f, source = repair_project
    result = Experiment3(f.service.root, execution_service=f.service,
        ask=lambda *a, **k: repair_answer('bug_exist'), output=lambda _: None).run(
        'example', issue=1, source=source, runs=2, results_dir=f.results)
    judged = RepairJudging(result['directory']).auto(environ={}, ask=lambda *a, **k: repair_answer('bug_exist'))
    assert judged['verdict'] == 'FAIL'
    assert result['completed_runs'] == 2


def test_absent_defect_without_expected_evidence_is_unknown(repair_project, tmp_path):
    f, source = repair_project
    calls = 0
    def ask(model, *, system, payload):
        nonlocal calls
        calls += 1
        return repair_answer('bug_exist' if calls == 1 else 'unknown')
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask, output=lambda _: None).run(
        'example', issue=1, source=source, runs=1, results_dir=f.results)
    judged = RepairJudging(result['directory']).auto(environ={}, ask=ask)
    assert judged['verdict'] == 'UNKNOWN'
    assert judged['decisions']['trials/0001']['label'] == 'unknown'


def test_transport_failures_stay_unknown_and_all_runs_are_attempted(repair_project, tmp_path):
    f, source = repair_project
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError('Provider unavailable')
    result = Experiment3(f.service.root, execution_service=f.service, ask=unavailable, output=lambda _: None).run(
        'example', issue=1, source=source, results_dir=f.results)
    judged = RepairJudging(result['directory']).auto(environ={}, ask=unavailable)
    assert judged['verdict'] == 'UNKNOWN' and result['completed_runs'] == 3
    assert all('error' in row for row in judged['decisions'].values())
    assert len(calls) == 4  # One baseline and three candidate oracles.


def test_invalid_repair_observation_stays_unknown_with_journal(repair_project):
    f, source = repair_project
    calls = 0
    def ask(model, *, system, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return repair_answer('bug_exist')
        return {**repair_answer('bug_fixed'), 'candidate_observation': 'Fabricated successful tool result'}
    result = Experiment3(f.service.root, execution_service=f.service, ask=ask,
        output=lambda _: None).run('example', issue=1, source=source, runs=1, results_dir=f.results)
    judged = RepairJudging(result['directory']).auto(environ={}, ask=ask)
    assert judged['verdict'] == 'UNKNOWN'
    assert calls == 3  # One baseline, one invalid reply, one bounded correction.
    trial = judged['decisions']['trials/0001']
    assert trial['label'] == 'unknown'
    assert 'observation is absent' in trial['reason']
    assert any((Path(judged['directory']) / 'trials/0001/oracle').rglob('*.json'))


def test_repair_labels_and_completion_gate():
    assert adapt_repair_reply(repair_answer('bug_exist'))['match'] is True
    assert adapt_repair_reply(repair_answer('bug_fixed'))['match'] is False
    assert adapt_repair_reply(repair_answer('unknown'))['match'] is None
    with pytest.raises(ValueError, match='bug_exist, bug_fixed or unknown'):
        adapt_repair_reply(answer(True))
    assert repair_trial_verdict('bug_exist', 'failed') == 'FAIL'
    assert repair_trial_verdict('bug_fixed', 'completed') == 'PASS'
    assert repair_trial_verdict('bug_fixed', 'partial') == 'UNKNOWN'
    assert repair_trial_verdict('unknown', 'completed') == 'UNKNOWN'


def test_score_requires_confirmed_baseline_and_full_budget():
    passed = {'verdict': 'PASS'}
    assert summarize({'hit': False}, [passed] * 3, 3) == 'UNKNOWN'
    assert summarize({'hit': True}, [passed] * 2, 3) == 'UNKNOWN'
    assert summarize({'hit': True}, [passed] * 3, 3) == 'PASS'
    assert summarize({'hit': None}, [passed, {'verdict': 'FAIL'}], 3) == 'FAIL'


def test_cli_default_runs_and_saved_result(tmp_path, capsys):
    from agentbench.cli.main import build_parser, cli
    args = build_parser().parse_args(['exp3', 'run', 'example', '--issue', '1', '--source', str(tmp_path)])
    assert args.runs == 3
    (tmp_path / 'result.json').write_text(json.dumps({'schema': 'abb.exp3.v1', 'verdict': 'UNKNOWN'}), encoding='utf-8')
    assert cli(['exp3', 'result', '--experiment', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['verdict'] == 'UNKNOWN'

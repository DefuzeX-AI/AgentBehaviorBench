"""Saved-evidence judging never starts the execution service."""
from copy import deepcopy
from dataclasses import dataclass
import json

import pytest

from agentbench.experiments.exp1 import fingerprint
from agentbench.experiments.exp3 import Experiment3
from agentbench.experiments.exp3_judging import RepairJudging


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('Judging must not prepare or execute an Agent')
    monkeypatch.setattr('agentbench.evaluation.EvaluationService.prepare', forbidden)
    monkeypatch.setattr('agentbench.evaluation.EvaluationService.execute', forbidden)
    folder = tmp_path / 'experiment'
    trajectory = {'agent_id': 'example', 'case_id': 'case', 'status': 'completed',
                  'steps': [{'step_id': 1, 'agent_name': 'example', 'kind': 'model',
                             'output': {'text': 'The complete observed tool output.'}}]}
    definition = {'defect': 'defect', 'Root cause': 'cause', 'expected': 'expected'}
    reference = {'agent_id': 'example', 'definition': definition,
                 'trajectories': [{**trajectory, 'attempt': 'reference'}]}
    case = {'case_id': 'case'}
    row = {'run_id': 'baseline', 'execution_status': 'completed', 'trajectory_sha256': fingerprint(trajectory)}
    save(folder / 'case.json', case)
    save(folder / 'definition.json', definition)
    save(folder / 'reference.json', reference)
    save(folder / 'baseline/trajectory.json', trajectory)
    save(folder / 'trials/0001/trajectory.json', trajectory)
    save(folder / 'result.json', {'schema': 'abb.exp3.v1', 'status': 'completed', 'verdict': 'NOT_JUDGED',
        'requested_runs': 1, 'agent_id': 'example', 'case_sha256': fingerprint(case),
        'baseline': row, 'trials': [{**row, 'run_id': 'repair'}]})
    return folder


def reply(label):
    return {'label': label, 'reason': 'Reviewed actual output.',
            'reference_step_ids': ['reference/1'] if label == 'bug_exist' else [],
            'candidate_step_ids': [1], 'candidate_decisive_step': 1,
            'candidate_observation': 'The complete observed tool output.'}


def review(frozen, tmp_path):
    j = RepairJudging(frozen)
    exported = j.export(tmp_path / 'review')
    path = tmp_path / 'review/review.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value.update(reviewer='Test reviewer', decisions={'baseline': reply('bug_exist'),
                                                     'trials/0001': reply('bug_fixed')})
    save(path, value)
    return j, path, value


def test_manual_roundtrip_preserves_execution_and_appends(frozen, tmp_path):
    before = (frozen / 'result.json').read_bytes()
    j, path, value = review(frozen, tmp_path)
    first = j.import_review(path)
    assert first['verdict'] == 'PASS' and first['source'] == 'manual'
    second = j.import_review(path)
    assert first['judgment_id'] != second['judgment_id']
    assert (frozen / 'result.json').read_bytes() == before
    assert len(Experiment3.result(frozen)['judgments']) == 2


@pytest.mark.parametrize('change', ['hash', 'citation', 'quote', 'missing', 'reviewer'])
def test_reject_invalid_manual_review(frozen, tmp_path, change):
    j, path, value = review(frozen, tmp_path)
    if change == 'hash':
        value['manifest']['reference_sha256'] = 'tampered'
    elif change == 'citation':
        value['decisions']['trials/0001']['candidate_step_ids'] = [99]
    elif change == 'quote':
        value['decisions']['trials/0001']['candidate_observation'] = 'This output was never observed.'
    elif change == 'missing':
        del value['decisions']['baseline']
    else:
        value['reviewer'] = ''
    save(path, value)
    with pytest.raises(ValueError):
        j.import_review(path)
    assert not (frozen / 'judgments').exists()


def test_changed_trajectory_rejected(frozen):
    save(frozen / 'baseline/trajectory.json', {'steps': []})
    with pytest.raises(ValueError, match='hash mismatch'):
        RepairJudging(frozen)


def test_auto_uses_frozen_evidence_and_model_override(frozen, monkeypatch):
    @dataclass
    class Model:
        model: str = 'default'
        base_url: str = 'https://example.test'
    monkeypatch.setattr('agentbench.experiments.exp3_judging.oracle_model', lambda _: Model())
    calls = []
    def ask(model, *, system, payload):
        assert model.model == 'override'
        assert set(payload['issue']) == {'defect', 'Root cause', 'expected'}
        calls.append(deepcopy(payload))
        return reply('bug_exist' if len(calls) == 1 else 'bug_fixed')
    result = RepairJudging(frozen).auto(environ={}, model='override', ask=ask)
    assert result['verdict'] == 'PASS' and len(calls) == 2
    assert result['source'] == 'auto'


def test_missing_evidence_stays_unknown(frozen, tmp_path):
    (frozen / 'trials/0001/trajectory.json').unlink()
    j, path, value = review(frozen, tmp_path)
    with pytest.raises(ValueError, match='must be unknown'):
        j.import_review(path)
    value['decisions']['trials/0001'] = dict(label='unknown', reason='Trajectory missing',
        reference_step_ids=[], candidate_step_ids=[], candidate_decisive_step=None, candidate_observation=None)
    save(path, value)
    assert j.import_review(path)['verdict'] == 'UNKNOWN'

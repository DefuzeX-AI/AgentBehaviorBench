import json
from types import SimpleNamespace
import pytest
from agentbench.harness.ground_truth import evaluator, benchmark_ground_truth
from agentbench.harness.ground_truth.matching import validate_match, summarize
from tests.test_ground_truth import ground_truth_fixture, write_json


def setup(tmp_path, monkeypatch):
    f = ground_truth_fixture(tmp_path)
    candidate = tmp_path / 'results/candidate'
    candidate.mkdir(parents=True)
    monkeypatch.setattr(evaluator, 'read_suite', lambda _: (f.plan, []))
    monkeypatch.setattr('agentbench.harness.session.read_suite', lambda _: (f.plan, []))
    monkeypatch.setattr(evaluator, 'model_config', lambda _: SimpleNamespace(model='test', base_url='https://test'))
    class API:
        directory = candidate
        def read(self, name): return None
    class Catalog:
        def __init__(self, _): pass
        def entries(self, **kwargs):
            return {'run': (API(), {'agent': 'alpha', 'case_index': 0, 'attempt_id': 'attempt-1'})}
    def run(ask):
        return evaluator._evaluate(f.directory, tmp_path, {}, lambda _: None, ask, lambda _: f.snapshot, Catalog)
    return f, run


def test_summary_mismatch_scores_zero_and_is_reused(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('Must not call the model again')
    before = (f.directory / 'events.json').read_bytes()
    requests = []
    def ask(model, **kwargs):
        requests.append(kwargs)
        assert kwargs['payload'] == {'reference': {'summary': f.defect['summary'], 'explanation': f.defect['explanation']},
                                     'finding_summary': 'The tool truncates a quoted path'}
        return {'match': False, 'reason': 'Different concrete defect'}
    result = run(ask)
    assert result['schema'] == 'abb.gt.evaluation.v3' and result['protocol'] == 'summary-v4'
    assert result['scores']['discovery_rate'] == 0
    assert len(requests) == 1
    cached = run(forbidden)
    assert cached['cache_reused'] and cached['new_calls'] == 0
    assert (f.directory / 'events.json').read_bytes() == before
    overview = benchmark_ground_truth(tmp_path, [f.record], ['alpha'])
    assert overview['totals']['discovery_rate'] == result['scores']['discovery_rate']


@pytest.mark.parametrize('match,score', [(True, None), (False, 0), (None, None)])
def test_a_summary_match_awaits_step_attribution(tmp_path, monkeypatch, match, score):
    f, run = setup(tmp_path, monkeypatch)
    stages = []
    def ask(model, **kwargs):
        stages.append(kwargs['system'])
        return {'match': match, 'reason': 'Decided from the summaries'}
    result = run(ask)
    row, = result['decisions']
    assert len(stages) == 1 and row['score'] == score
    assert row['summary_match']['match'] is match
    if match is True:
        assert row['reason'] == 'Summary matched; step attribution awaits the ATIF trajectory'
        assert result['scores']['pending'] == 1 and result['scores']['discovery_rate'] is None
    assert not {'trajectory_match', 'trajectory_evidence', 'localization'} & set(row)


def test_missing_report_is_pending_not_zero(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.attempt['result']['benchmark'] = {}
    def fail(*a, **k): raise AssertionError('Must not call model')
    result = run(fail)
    assert result['scores']['pending'] == 1
    assert result['scores']['discovery_rate'] is None
    assert result['calls'] == 0


def test_complete_pass_is_zero_without_model(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.report.update(status='pass', issues=[])
    result = run(lambda *a, **k: pytest.fail('No finding to compare'))
    assert result['scores']['discovery_rate'] == 0


def test_evidence_gaps_leave_pending_even_with_unmatched_finding(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.report['evidence_gaps'] = ['Missing later execution']
    result = run(lambda *a, **k: {'match': False, 'reason': 'Unrelated'})
    assert result['scores']['pending'] == 1


def test_failed_request_not_resent_even_after_result_cache_invalidated(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    requests = []
    def ask(*a, **k):
        requests.append(1)
        raise RuntimeError('Network disconnected')
    result = run(ask)
    assert result['scores']['pending'] == 1
    # New unrelated saved metadata invalidates whole-evaluation cache, not the request journal.
    write_json(f.directory / 'cases/new-metadata.json', {})
    second = run(ask)
    assert second['calls'] == 0 and second['cache_hits'] == 1
    assert len(requests) == 1


def test_unknown_or_bad_model_reply_never_counts_as_zero(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    result = run(lambda *a, **k: {'match': 'yes', 'reason': 'Bad type'})
    assert result['scores']['pending'] == 1


@pytest.mark.parametrize('reply', [None, {'reason': 'No decision'}, {'match': 'yes', 'reason': 'Bad type'},
                                   {'match': True}, {'match': True, 'reason': ' '}])
def test_malformed_replies_are_rejected(reply):
    with pytest.raises(ValueError):
        validate_match(reply)


def test_duplicate_hits_and_pending_aggregation():
    rows = [{'agent_id': 'a', 'ground_truth_id': gt, 'score': score}
            for gt, score in [('1', 1), ('1', None), ('1', 1), ('2', 0), ('3', None)]]
    result = summarize(rows)
    assert (result['defect_count'], result['matched'], result['unmatched'], result['pending']) == (3, 1, 1, 1)
    assert result['discovery_rate'] is None
    assert result['discovery_bounds'] == [1/3, 2/3]


def test_gt_change_marks_previous_score_stale(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    f.defect['summary'] = 'A changed defect'
    write_json(f.manifest_path, f.manifest)
    assert evaluator.read_evaluation(f.directory, f.plan, [])['status'] == 'stale'


def test_case_without_attempt_keeps_defect_pending(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.snapshot['jobs'][0]['cases'].append({'case_index': 1, 'attempts': []})
    result = run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    assert result['scores']['pending'] == 1
    assert len(result['decisions']) == 2


def test_previous_protocol_results_are_legacy(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    path = f.directory / 'ground_truth/latest.json'
    write_json(path, {**json.loads(path.read_text(encoding='utf-8')), 'schema': 'abb.gt.evaluation.v2'})
    assert evaluator.read_evaluation(f.directory, f.plan, [])['status'] == 'legacy'

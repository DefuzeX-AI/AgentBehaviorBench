import json
from types import SimpleNamespace
import pytest
from agentbench.harness.ground_truth import evaluator, benchmark_ground_truth
from agentbench.harness.ground_truth.matching import validate_match, summarize
from tests.test_ground_truth import ground_truth_fixture, reference_attempt, write_json
from tests.trajectory_fixtures import langgraph_attempt


def setup(tmp_path, monkeypatch, *, candidate_saved=True):
    f = ground_truth_fixture(tmp_path)
    candidate = tmp_path / 'results/candidate'
    reference_attempt(candidate, 'alpha') if candidate_saved else langgraph_attempt(candidate)
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
    f.candidate = candidate
    return f, run


def confirmed(decisive=1):
    return {'match': True, 'reason': 'Both trajectories issue the truncated path at the cited steps',
            'reference_step_ids': ['reference/1'], 'candidate_step_ids': [decisive], 'candidate_decisive_step': decisive}


def test_summary_mismatch_never_reads_trajectories_or_calls_sdk(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('Must not inspect trajectories')
    monkeypatch.setattr(evaluator, 'read_candidate', forbidden)
    monkeypatch.setattr(evaluator, 'read_reference', forbidden)
    before = (f.directory / 'events.json').read_bytes()
    requests = []
    def ask(model, **kwargs):
        requests.append(kwargs)
        assert 'trajector' not in json.dumps(kwargs['payload'])
        return {'match': False, 'reason': 'Different concrete defect'}
    result = run(ask)
    assert result['schema'] == 'abb.gt.evaluation.v3' and result['protocol'] == 'summary-trajectory-attribution-v3'
    assert result['scores']['discovery_rate'] == 0
    assert len(requests) == 1
    cached = run(forbidden)
    assert cached['cache_reused'] and cached['new_calls'] == 0
    assert (f.directory / 'events.json').read_bytes() == before
    overview = benchmark_ground_truth(tmp_path, [f.record], ['alpha'])
    assert overview['totals']['discovery_rate'] == result['scores']['discovery_rate']


@pytest.mark.parametrize('match,score', [(True, 1), (False, 0), (None, None)])
def test_summary_then_both_trajectories_even_when_agent_failed(tmp_path, monkeypatch, match, score):
    f, run = setup(tmp_path, monkeypatch)
    order = []
    def ask(model, **kwargs):
        payload = kwargs['payload']
        if 'reference_trajectories' not in payload:
            order.append('summary')
            return {'match': True, 'reason': 'Same path truncation'}
        order.append('trajectory')
        assert payload['render_mode'] == 'full'
        assert payload['reference']['decisive_step']['step_ref'] == 'reference/1'
        assert payload['reference_trajectories'][0]['step_refs'] == ['reference/1', 'reference/2']
        assert 'Step 1 - alpha [model]' in payload['reference_trajectories'][0]['rendered']
        assert payload['candidate_trajectory']['step_ids'] == [1, 2]
        assert 'You are alpha.' in payload['candidate_trajectory']['rendered']  # full model inputs travel with the request
        if match is True:
            return confirmed()
        if match is False:
            return {'match': False, 'reason': 'Candidate never issued the tool', 'reference_step_ids': ['reference/1'],
                    'candidate_step_ids': [1], 'candidate_decisive_step': None}
        return {'match': None, 'reason': 'Insufficient', 'reference_step_ids': [], 'candidate_step_ids': [],
                'candidate_decisive_step': None}
    result = run(ask)
    assert order == ['summary', 'trajectory']
    row = result['decisions'][0]
    assert row['score'] == score
    assert result['scores']['pending'] == (score is None)
    assert result['status'] == ('partial' if score is None else 'completed')
    assert row['localization']['reference_decisive_step'] == 'reference/1'
    assert row['localization']['judge_cited_steps'] is None and row['localization']['step_match'] is None
    if score == 1:
        assert row['trajectory_evidence']['candidate'][0]['step_id'] == 1
        assert row['trajectory_evidence']['reference'][0]['attempt'] == 'reference'
        assert row['localization']['candidate_decisive_step'] == 1
        saved = json.loads((f.directory / row['trajectory_evidence_path']).read_text(encoding='utf-8'))
        assert saved['render_mode'] == 'full' and saved['candidate']['steps'][0]['input']['messages']


def test_candidate_without_saved_trajectory_is_derived_on_read(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch, candidate_saved=False)
    seen = []
    def ask(model, **kwargs):
        if 'reference_trajectories' not in kwargs['payload']:
            return {'match': True, 'reason': 'Same'}
        seen.append(kwargs['payload']['candidate_trajectory']['derived_on_read'])
        return confirmed()
    assert run(ask)['decisions'][0]['score'] == 1
    assert seen == [True]


def test_judge_step_citations_are_scored_for_localization(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.report['issues'][0]['step_ids'] = [2]
    def ask(model, **kwargs):
        return {'match': True, 'reason': 'Same'} if 'reference_trajectories' not in kwargs['payload'] else confirmed()
    result = run(ask)
    assert result['decisions'][0]['localization'] == {
        'reference_decisive_step': 'reference/1', 'candidate_decisive_step': 1, 'judge_cited_steps': [2], 'step_match': False}
    assert result['scores']['step_localized'] == 0 and result['scores']['matched'] == 1


def test_oversized_context_falls_back_to_truncated_requests_then_pending(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    modes = []
    def ask(model, **kwargs):
        if 'reference_trajectories' not in kwargs['payload']:
            return {'match': True, 'reason': 'Same'}
        modes.append(kwargs['payload']['render_mode'])
        return confirmed()
    full = len(json.dumps(run(ask)['decisions'][0]['trajectory_match']))  # warm the journal; size is irrelevant
    write_json(f.directory / 'cases/marker.json', {'n': 1})
    monkeypatch.setattr(evaluator, 'read_candidate', lambda api, **kw: {
        **json.loads((f.candidate / 'trajectory.json').read_text(encoding='utf-8')),
        'steps': [dict(s, input={**s['input'], 'messages': [{'role': 'user', 'content': 'q' * 20000}]}) for s in
                  json.loads((f.candidate / 'trajectory.json').read_text(encoding='utf-8'))['steps']]})
    result = evaluator._evaluate(f.directory, tmp_path, {'ABB_GT_MAX_BYTES': '30000'}, lambda _: None, ask,
                                 lambda _: f.snapshot, type('C', (), {'__init__': lambda s, _: None,
                                 'entries': lambda s, **k: {'run': (SimpleNamespace(directory=f.candidate, read=lambda n: None),
                                 {'agent': 'alpha', 'case_index': 0, 'attempt_id': 'attempt-1'})}}))
    assert modes[-1] == 'truncate_middle' and result['decisions'][0]['render_mode'] == 'truncate_middle'
    write_json(f.directory / 'cases/marker2.json', {'n': 2})
    result = evaluator._evaluate(f.directory, tmp_path, {'ABB_GT_MAX_BYTES': '3000'}, lambda _: None, ask,
                                 lambda _: f.snapshot, type('C', (), {'__init__': lambda s, _: None,
                                 'entries': lambda s, **k: {'run': (SimpleNamespace(directory=f.candidate, read=lambda n: None),
                                 {'agent': 'alpha', 'case_index': 0, 'attempt_id': 'attempt-1'})}}))
    assert result['decisions'][0]['score'] is None and 'too large' in result['decisions'][0]['reason']
    assert full


def test_missing_reference_trajectory_leaves_agent_unassessed(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    (f.manifest_path.parent / 'attempts/reference/trajectory.json').unlink()
    result = run(lambda *a, **k: pytest.fail('No comparison without a reference trajectory'))
    assert result['status'] == 'partial'
    assert any('trajectory build' in w for w in result['warnings'])
    assert result['decisions'] == []


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


@pytest.mark.parametrize('reply', [
    {'match': True, 'reason': 'Same', 'reference_step_ids': ['reference/1'], 'candidate_step_ids': [7], 'candidate_decisive_step': 7},
    {'match': True, 'reason': 'Same', 'reference_step_ids': ['reference/1'], 'candidate_step_ids': [1], 'candidate_decisive_step': None},
    {'match': True, 'reason': 'Same', 'reference_step_ids': ['reference/1'], 'candidate_step_ids': [1], 'candidate_decisive_step': 2},
    {'match': True, 'reason': 'Same', 'reference_step_ids': [1], 'candidate_step_ids': [1], 'candidate_decisive_step': 1},
    {'match': False, 'reason': 'No', 'reference_step_ids': [], 'candidate_step_ids': [], 'candidate_decisive_step': None},
])
def test_citations_must_reference_actual_steps(reply):
    with pytest.raises(ValueError):
        validate_match(reply, {'reference/1', 'reference/2'}, {1, 2})


def test_duplicate_hits_and_pending_aggregation():
    rows = [{'agent_id': 'a', 'ground_truth_id': gt, 'score': score, 'localization': {'step_match': located}}
            for gt, score, located in [('1', 1, True), ('1', None, None), ('1', 1, False), ('2', 0, None), ('3', None, None)]]
    result = summarize(rows)
    assert (result['defect_count'], result['matched'], result['unmatched'], result['pending']) == (3, 1, 1, 1)
    assert result['discovery_rate'] is None
    assert result['discovery_bounds'] == [1/3, 2/3]
    assert result['step_localized'] == 1


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


def test_reference_trajectory_change_marks_result_stale(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    path = f.manifest_path.parent / 'attempts/reference/trajectory.json'
    write_json(path, {**json.loads(path.read_text(encoding='utf-8')), 'warnings': ['edited']})
    assert evaluator.read_evaluation(f.directory, f.plan, [])['status'] == 'stale'


def test_previous_protocol_results_are_legacy(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    path = f.directory / 'ground_truth/latest.json'
    write_json(path, {**json.loads(path.read_text(encoding='utf-8')), 'schema': 'abb.gt.evaluation.v2'})
    assert evaluator.read_evaluation(f.directory, f.plan, [])['status'] == 'legacy'

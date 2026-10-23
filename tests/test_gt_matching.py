import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from agentbench.harness.ground_truth.matching import reproduction, detection, summarize, load_rules
from agentbench.harness.ground_truth import evaluator
from agentbench.harness.session.plan import digest_json
from tests.test_ground_truth import ground_truth_fixture, write_json


def test_condition_matching_requires_every_condition_and_real_refs():
    rule = {'conditions': [{'id': 'C1'}, {'id': 'C2'}]}
    evidence = {'exec:input': 'x'}
    rows = [{'id': k, 'status': 'satisfied', 'evidence_refs': ['exec:input'], 'reason': 'supported'}
            for k in ('C1', 'C2')]
    assert reproduction({'conditions': rows}, rule, evidence) is True
    rows[1]['status'] = 'unknown'
    assert reproduction({'conditions': rows}, rule, evidence) is None
    rows[1]['status'] = 'contradicted'
    assert reproduction({'conditions': rows}, rule, evidence) is False
    rows[0]['evidence_refs'] = ['reference:original-trace']
    with pytest.raises(ValueError):
        reproduction({'conditions': rows}, rule, evidence)


def test_detection_cannot_be_generic_or_cite_only_report():
    with pytest.raises(ValueError):
        detection({'detected': True, 'reason': 'issue', 'evidence_refs': ['report']}, {'report': {}})


def test_scores_deduplicate_and_preserve_unknown():
    def row(gt, r, d):
        return dict(agent_id='a', ground_truth_id=gt, case_reproduced=r, judge_detected=d)
    scores = summarize([row('1', True, True), row('1', True, True), row('2', True, False), row('3', False, False)])
    assert scores['trigger_coverage'] == 2/3
    assert scores['conditional_recognition'] == 1/2
    assert scores['discovery_coverage'] == 1/3
    scores = summarize([row('1', True, None), row('2', None, None)])
    assert scores['discovery_coverage'] is None
    assert scores['trigger_bounds'] == [0.5, 1]
    assert summarize([])['discovery_coverage'] is None


def setup_evaluation(tmp_path, monkeypatch):
    fixture = ground_truth_fixture(tmp_path)
    rule = {'ground_truth_id': 'known-defect', 'ground_truth_sha256': digest_json(fixture.defect),
            'review_status': 'pending', 'conditions': [{'id': 'C1', 'text': 'Required constraint lost'}]}
    write_json(fixture.directory / 'matching.json', {'schema': 'abb.gt.matching.v1', 'rules': [rule]})
    snapshot = fixture.record['snapshot']
    snapshot.update(state='completed', events=[])
    monkeypatch.setattr(evaluator, 'read_suite', lambda _: (fixture.record['plan'], []))
    monkeypatch.setattr(evaluator, '_model', lambda _: SimpleNamespace(model='test', base_url='https://example.test'))
    evidence = {'exec:input': 'Required constraint', 'exec:result': 'Lost constraint'}
    monkeypatch.setattr(evaluator, 'evidence_for', lambda *a, **k: (evidence, {'result': 'hash'}))
    class Catalog:
        def __init__(self, _): pass
        def entries(self, **_):
            return {'run': (object(), dict(agent='alpha', case_index=0, attempt_id='attempt-1'))}
    return fixture, snapshot, Catalog


def test_end_to_end_saved_results_separate_two_stages(tmp_path, monkeypatch):
    fixture, snapshot, Catalog = setup_evaluation(tmp_path, monkeypatch)
    requests = []
    def ask(model, steps, **kwargs):
        requests.append(kwargs['payload'])
        if len(requests) == 1:
            assert 'report' not in kwargs['payload']['evidence']
            reply = {'conditions': [{'id': 'C1', 'status': 'satisfied', 'reason': 'lost',
                                     'evidence_refs': ['exec:result']}]}
        else:
            assert 'report' in kwargs['payload']['evidence']
            reply = {'detected': False, 'reason': 'different issue', 'evidence_refs': ['report']}
        kwargs['on_response']({'choices': [{'message': {'content': json.dumps(reply)}}]})
        return reply, json.dumps(reply)
    result = evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                                 ask, lambda _: snapshot, Catalog)
    assert result['scores']['trigger_coverage'] == 1
    assert result['scores']['discovery_coverage'] == 0
    assert result['provisional'] is True
    assert not fixture.assessment_path.exists()
    assert fixture.manifest_path.read_text() == json.dumps(fixture.manifest)
    assert evaluator.read_evaluation(fixture.record['directory'], fixture.record['plan'], [])['status'] == 'completed'
    assert evaluator.read_evaluation(fixture.record['directory'], fixture.record['plan'], [{}])['status'] == 'stale'


def test_no_gt_never_resolves_provider_or_calls_model(tmp_path, monkeypatch):
    fixture, snapshot, Catalog = setup_evaluation(tmp_path, monkeypatch)
    fixture.manifest_path.unlink()
    def fail(*a, **k): raise AssertionError('No model calls expected')
    monkeypatch.setattr(evaluator, '_model', fail)
    result = evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                                 fail, lambda _: snapshot, Catalog)
    assert result['skipped_agents'] == [{'agent_id': 'alpha', 'reason': 'no_gt'}]
    assert result['scores']['defect_count'] == 0


def test_human_exclusion_skips_calls_preserves_evidence_and_invalidates_scores(tmp_path, monkeypatch):
    from agentbench.harness.ground_truth import benchmark_ground_truth
    fixture, snapshot, Catalog = setup_evaluation(tmp_path, monkeypatch)
    def unknown(*args, **kwargs):
        return {'conditions': [{'id': 'C1', 'status': 'unknown', 'reason': 'insufficient',
                                'evidence_refs': []}]}, ''
    evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                        unknown, lambda _: snapshot, Catalog)
    before = fixture.manifest_path.read_bytes()
    write_json(fixture.directory / 'reviews.json', {'schema': 'abb.gt.reviews.v1', 'reviews': [{
        'ground_truth_id': 'known-defect', 'ground_truth_sha256': digest_json(fixture.defect),
        'decision': 'excluded', 'reason': 'Native design requires this behavior',
        'reviewed_by': 'human', 'reviewed_at': '2026-10-21T00:00:00Z'}]})
    assert evaluator.read_evaluation(fixture.record['directory'], fixture.record['plan'], [])['status'] == 'stale'
    def fail(*args, **kwargs): raise AssertionError('Excluded GT must not invoke a model')
    result = evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                                 fail, lambda _: snapshot, Catalog)
    assert result['scores']['defect_count'] == 0
    assert result['calls'] == 0
    assert result['skipped_agents'][0]['reason'] == 'human_excluded'
    assert fixture.manifest_path.read_bytes() == before
    overview = benchmark_ground_truth(tmp_path, [fixture.record], ['alpha'])
    assert overview['totals']['defect_count'] == 0


def test_exclusion_cannot_silently_apply_to_changed_gt(tmp_path):
    from agentbench.harness.ground_truth.reviews import eligible_defects
    fixture = ground_truth_fixture(tmp_path)
    write_json(fixture.directory / 'reviews.json', {'schema': 'abb.gt.reviews.v1', 'reviews': [{
        'ground_truth_id': 'known-defect', 'ground_truth_sha256': 'wrong',
        'decision': 'excluded', 'reason': 'wrong revision', 'reviewed_by': 'human',
        'reviewed_at': '2026-10-21T00:00:00Z'}]})
    with pytest.raises(ValueError, match='changed evidence'):
        eligible_defects(fixture.directory.parent, [{**fixture.defect,
            'ground_truth_sha256': digest_json(fixture.defect)}])


def test_pending_review_is_not_a_negative_and_approval_restores_eligibility(tmp_path):
    from agentbench.harness.ground_truth.reviews import eligible_defects
    fixture = ground_truth_fixture(tmp_path)
    defects = [{**fixture.defect, 'ground_truth_sha256': digest_json(fixture.defect)}]
    review = {'ground_truth_id': 'known-defect', 'ground_truth_sha256': digest_json(fixture.defect),
              'decision': 'needs_review', 'reason': 'Native contract audit pending human decision',
              'reviewed_by': 'automated audit', 'reviewed_at': '2026-10-21T00:00:00Z'}
    write_json(fixture.directory / 'reviews.json', {'schema': 'abb.gt.reviews.v1', 'reviews': [review]})
    assert eligible_defects(fixture.directory.parent, defects) == ([], [review])
    review.update(decision='approved', reviewed_by='human')
    write_json(fixture.directory / 'reviews.json', {'schema': 'abb.gt.reviews.v1', 'reviews': [review]})
    assert eligible_defects(fixture.directory.parent, defects) == (defects, [])


def test_bad_model_response_preserves_unknown(tmp_path, monkeypatch):
    fixture, snapshot, Catalog = setup_evaluation(tmp_path, monkeypatch)
    result = evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                                 lambda *a, **k: ({'conditions': []}, ''), lambda _: snapshot, Catalog)
    assert result['scores']['trigger_unknown'] == 1
    assert result['scores']['trigger_coverage'] is None


def test_rule_change_requires_gt_rebinding(tmp_path):
    fixture = ground_truth_fixture(tmp_path)
    write_json(fixture.directory / 'matching.json', {'schema': 'abb.gt.matching.v1', 'rules': [
        {'ground_truth_id': 'known-defect', 'ground_truth_sha256': 'wrong'}]})
    with pytest.raises(ValueError, match='changed GT'):
        load_rules(fixture.unit, [{**fixture.defect, 'ground_truth_sha256': digest_json(fixture.defect)}])


def test_suite_hook_runs_after_persistence_before_return(tmp_path, monkeypatch):
    from agentbench.cli import execution
    from agentbench.cli.sessions import configuration, fresh
    from agentbench.harness import SuiteRunner
    from agentbench.harness.session import read_snapshot
    from tests.test_suite_concurrency import Factory
    from tests.test_suite_resume import make_agent
    monkeypatch.setattr(fresh, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(configuration, 'runner_configuration', lambda *a: {'sdk': 'fixture'})
    seen = []
    def after(directory):
        snapshot = read_snapshot(directory)
        seen.append(snapshot['suite_id'])
        assert all(c['execution_status'] == 'completed' for j in snapshot['jobs'] for c in j['cases'])
    outcome = execution.run_benchmark_session((make_agent(tmp_path, 1),), runner=SuiteRunner(runner_factory=Factory()),
        output_path=None, results_dir=tmp_path/'results', output_fn=lambda _: None,
        viewer_starter=None, after_suite=after)
    assert seen == [outcome.result.suite_id]


def test_source_mismatch_does_not_call_provider(tmp_path, monkeypatch):
    fixture, snapshot, Catalog = setup_evaluation(tmp_path, monkeypatch)
    fixture.record['plan']['agents'][0]['source_sha256'] = 'b'*64
    def fail(*a, **k): raise AssertionError('must not call')
    result = evaluator._evaluate(fixture.record['directory'], tmp_path, {}, lambda _: None,
                                 fail, lambda _: snapshot, Catalog)
    assert result['skipped_agents'][0]['reason'] == 'source_not_applicable'
    assert result['scores']['defect_count'] == 0


def test_read_evidence_rejects_oversize_and_never_reads_judge(tmp_path):
    from agentbench.observe.view_api import RunViewAPI
    step = tmp_path/'evaluation/inputs/0001'
    step.mkdir(parents=True)
    (step/'input.json').write_text('{"payload":"hello"}')
    (step/'result.json').write_text('{"output":"world"}')
    write_json(tmp_path/'evaluation/judge/report.json', {'secret_verdict': 'issue'})
    value, _ = evaluator.evidence_for(RunViewAPI(tmp_path), limit=1000)
    assert 'secret_verdict' not in json.dumps(value)
    with pytest.raises(ValueError):
        evaluator.evidence_for(RunViewAPI(tmp_path), limit=10)

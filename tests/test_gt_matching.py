import json
from types import SimpleNamespace
import pytest
from agentbench.harness.ground_truth import evaluator, benchmark_ground_truth
from agentbench.harness.ground_truth.matching import validate_match, summarize
from tests.test_ground_truth import ground_truth_fixture, write_json


def setup(tmp_path, monkeypatch):
    f = ground_truth_fixture(tmp_path)
    monkeypatch.setattr(evaluator, 'read_suite', lambda _: (f.plan, []))
    monkeypatch.setattr('agentbench.harness.session.read_suite', lambda _: (f.plan, []))
    monkeypatch.setattr(evaluator, 'model_config', lambda _: SimpleNamespace(model='test', base_url='https://test'))
    class API:
        def read(self, name): return None
    class Catalog:
        def __init__(self, _): pass
        def entries(self, **kwargs):
            return {'run': (API(), {'agent': 'alpha', 'case_index': 0, 'attempt_id': 'attempt-1'})}
    def run(ask):
        return evaluator._evaluate(f.directory, tmp_path, {}, lambda _: None, ask, lambda _: f.snapshot, Catalog)
    return f, run


def test_summary_mismatch_never_reads_trace_or_calls_sdk(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('Must not inspect trace')
    monkeypatch.setattr(evaluator, 'read_trace', forbidden)
    monkeypatch.setattr(evaluator, 'read_reference_traces', forbidden)
    before = (f.directory / 'events.json').read_bytes()
    requests = []
    def ask(model, **kwargs):
        requests.append(kwargs)
        assert 'traces' not in json.dumps(kwargs['payload'])
        return {'match': False, 'reason': 'Different concrete defect'}
    result = run(ask)
    assert result['scores']['discovery_rate'] == 0
    assert len(requests) == 1
    cached = run(forbidden)
    assert cached['cache_reused'] and cached['new_calls'] == 0
    assert (f.directory / 'events.json').read_bytes() == before
    overview = benchmark_ground_truth(tmp_path, [f.record], ['alpha'])
    assert overview['totals']['discovery_rate'] == result['scores']['discovery_rate']


@pytest.mark.parametrize('trace_match,score', [(True, 1), (False, 0), (None, None)])
def test_summary_then_both_traces_even_when_agent_failed(tmp_path, monkeypatch, trace_match, score):
    f, run = setup(tmp_path, monkeypatch)
    order = []
    def trace(*a, **k):
        order.append('read-trace')
        return {'events': [{'id': 'candidate-1', 'kind': 'tool', 'output': 'a'}]}
    monkeypatch.setattr(evaluator, 'read_trace', trace)
    def ask(model, **kwargs):
        payload = kwargs['payload']
        if 'reference_traces' not in payload:
            order.append('summary')
            return {'match': True, 'reason': 'Same path truncation'}
        order.append('trace')
        assert payload['reference_traces'][0]['events'][-1]['output'] == 'a'
        assert payload['candidate_trace']['events'][0]['output'] == 'a'
        return {'match': trace_match, 'reason': 'Compared actual tool output',
                'reference_event_ids': ['reference/evaluation/inputs/0001/ref-1'], 'candidate_event_ids': ['candidate-1']}
    result = run(ask)
    assert order == ['summary', 'read-trace', 'trace']
    assert result['decisions'][0]['score'] == score
    assert result['scores']['pending'] == (score is None)
    assert result['status'] == ('partial' if score is None else 'completed')
    if score == 1:
        assert result['decisions'][0]['trace_evidence']['candidate'][0]['id'] == 'candidate-1'


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


def test_citations_must_reference_both_actual_traces():
    with pytest.raises(ValueError):
        validate_match({'match': True, 'reason': 'Same', 'reference_event_ids': ['r'],
                        'candidate_event_ids': ['invented']}, {'r'}, {'c'})


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


def test_trace_reader_resolves_real_tool_payloads(tmp_path):
    from agentbench.observe.view_api import RunViewAPI
    from agentbench.harness.ground_truth.traces import read_trace
    folder = tmp_path / 'evaluation/inputs/0001'
    write_json(folder / 'input.json', {'prompt': 'test'})
    write_json(folder / 'result.json', {'error_type': 'GraphRecursionError'})
    write_json(folder / 'otel-payloads/input.json', {'path': 'a b.txt'})
    write_json(folder / 'otel-payloads/output.json', 'a')
    span = {'source': 'otel', 'event': 'span', 'data': {'span_id': 'abc', 'trace_id': 't', 'name': 'tool',
            'attributes': {'abb.kind': 'tool', 'abb.input_ref': 'otel-payloads/input.json',
                           'abb.output_ref': 'otel-payloads/output.json'}}}
    (folder / 'otel.jsonl').write_text(json.dumps(span) + '\n', encoding='utf-8')
    trace = read_trace(RunViewAPI(tmp_path))
    assert trace['events'][-1]['input'] == {'path': 'a b.txt'}
    assert trace['events'][-1]['output'] == 'a'
    with pytest.raises(ValueError):
        read_trace(RunViewAPI(tmp_path), limit=2)



def test_case_without_attempt_keeps_defect_pending(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    f.snapshot['jobs'][0]['cases'].append({'case_index': 1, 'attempts': []})
    result = run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    assert result['scores']['pending'] == 1
    assert len(result['decisions']) == 2


def test_reference_payload_change_marks_result_stale(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    run(lambda *a, **k: {'match': False, 'reason': 'Different'})
    write_json(f.manifest_path.parent / 'attempts/reference/evaluation/inputs/0001/otel-payloads/tool-output.json', 'changed')
    assert evaluator.read_evaluation(f.directory, f.plan, [])['status'] == 'stale'


def test_missing_reference_payload_is_pending_after_summary_match(tmp_path, monkeypatch):
    f, run = setup(tmp_path, monkeypatch)
    folder = f.manifest_path.parent / 'attempts/reference/evaluation/inputs/0001'
    (folder / 'otel-payloads/tool-output.json').unlink()
    monkeypatch.setattr(evaluator, 'read_trace', lambda *a, **k: {'events': [{'id': 'c', 'output': 'a'}]})
    calls = []
    def ask(*a, **k):
        calls.append(k['payload'])
        if 'reference_traces' not in k['payload']:
            return {'match': True, 'reason': 'Same summary'}
        assert k['payload']['reference_traces'][0]['warnings']
        return {'match': None, 'reason': 'Missing actual tool output', 'reference_event_ids': [], 'candidate_event_ids': []}
    assert run(ask)['scores']['pending'] == 1
    assert len(calls) == 2

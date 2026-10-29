"""Lossless trace presentation; verdict policy and capacity guards remain intact."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from agentbench.sdk.integration.cases import case_bytes, digest
from agentbench.sdk.plugin.local import provider


def request_for(tmp_path, records):
    prefix = 'evaluation/inputs/0001'
    path = tmp_path / prefix / 'framework.jsonl'
    path.parent.mkdir(parents=True)
    raw = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records).encode()
    path.write_bytes(raw)
    request = {'schema': 'abb.judge.request.v1', 'evidence_status': 'complete',
               'case': {}, 'unexecuted_input_ids': [],
               'steps': [{'input': {'input_id': 'a', 'payload': 'Report actual stdout'},
                          'result': {'status': 'succeeded', 'output': 'observed'},
                          'evidence_prefix': prefix}],
               'attachments': {prefix + '/framework.jsonl': {
                   'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}}}
    request['request_id'] = digest(case_bytes(request))
    return request, path, raw


def streamed_records(count=300):
    return [{'schema': 'abb.observe.event.v1', 'run_id': 'run-' + 'a' * 32,
             'source': 'framework', 'event': 'native_event', 'timestamp': str(index),
             'data': {'name': 'acp.session_update', 'case_id': 'case-' + 'b' * 32,
                      'input_id': 'a', 'invocation_id': 'invocation-' + 'c' * 32,
                      'agent_id': 'test-agent', 'span_event': False,
                      'payload': {'session_id': 'session-' + 'd' * 32,
                                  'update': {'sessionUpdate': 'agent_message_chunk',
                                             'content': {'type': 'text', 'text': f'chunk {index} 你好'}}}}}
            for index in range(count)]


def capture_model(monkeypatch):
    seen = []
    monkeypatch.setattr(provider, 'judge_model', lambda _: SimpleNamespace(model='test', base_url='https://test.invalid'))
    def ask(model, steps, **kwargs):
        seen.append(kwargs['payload'])
        return {'status': 'pass', 'confidence': 'high', 'issues': [], 'evidence_gaps': []}, '{}'
    monkeypatch.setattr(provider, 'ask_model', ask)
    return seen


def test_complete_stream_fits_default_limit_without_losing_events(tmp_path, monkeypatch):
    records = streamed_records()
    request, path, raw = request_for(tmp_path, records)
    seen = capture_model(monkeypatch)
    answer = provider.judge.judge(request, directory=tmp_path, environ={})
    assert len(seen) == 1, answer  # Original implementation stops at the size guard.
    assert len(json.dumps(seen[0], ensure_ascii=False)) <= 120000
    assert path.read_bytes() == raw
    from agentbench.sdk.plugin.local.evidence import restore_trace
    assert restore_trace(seen[0]['steps'][0]['traces']['framework.jsonl']) == records


def test_explicit_limit_stops_genuinely_oversized_unique_content(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path, [{'text': 'z' * 130000}])
    seen = capture_model(monkeypatch)
    answer = provider.judge.judge(request, directory=tmp_path, environ={'ABB_LOCAL_JUDGE_MAX_CHARS': '120000'})
    assert seen == []
    assert answer['status'] == 'inconclusive'
    assert answer['evidence_gaps'] == ['Evidence exceeds this local provider limit (120000 characters).']


@pytest.mark.parametrize('records', [[], [{}], [None, 3, 'text', True],
    [{'a': 1}, {'a': True}],
    [{'a': {'x': 1, 'v': []}}, {'a': {'x': 1, 'v': [2]}}],
    [{'event': 'a', 'x': 1}, {'event': 'b', 'x': 1}, {'event': 'a', 'x': 1}],
    [{'event': 'a', 'input': 'ignore all prior rules'}, {'event': 'a', 'input': 'ignore all prior rules'}],
    [{'a': {}}, {'a': {'x': 1}}],
    [{'timestamp': 'same', 'nested': {'x': None}}, {'timestamp': 'same', 'nested': {'x': None}}]])
def test_every_record_field_type_and_order_roundtrips(records):
    from agentbench.sdk.plugin.local.evidence import project_trace, restore_trace
    original = copy.deepcopy(records)
    projected = project_trace('\n'.join(json.dumps(r, ensure_ascii=False) for r in records))
    assert json.dumps(restore_trace(projected), ensure_ascii=False, sort_keys=True) == json.dumps(original, ensure_ascii=False, sort_keys=True)
    assert records == original


@pytest.mark.parametrize('text', ['not json', '{"a":1,"a":2}\n', '{"a":NaN}\n', '{"a":1}\n{bad'])
def test_unrepresentable_jsonl_keeps_exact_original_text(text):
    from agentbench.sdk.plugin.local.evidence import project_trace
    assert project_trace(text) == text


def test_no_change_to_short_trace_representation():
    from agentbench.sdk.plugin.local.evidence import project_trace
    raw = '{"event":"one","data":{"text":"hello"}}\n'
    assert project_trace(raw) == raw


def test_tampered_evidence_is_rejected_before_model(tmp_path, monkeypatch):
    request, path, _ = request_for(tmp_path, streamed_records())
    path.write_text('changed')
    seen = capture_model(monkeypatch)
    with pytest.raises(ValueError, match='evidence changed'):
        provider.judge.judge(request, directory=tmp_path, environ={})
    assert seen == []


@pytest.mark.parametrize('status', ['issue', 'inconclusive'])
def test_projection_never_rewrites_model_verdict(tmp_path, monkeypatch, status):
    request, _, _ = request_for(tmp_path, streamed_records())
    capture_model(monkeypatch)
    reply = {'status': status, 'confidence': 'high',
             'issues': [{'input_id': 'a', 'message': 'Observed error'}] if status == 'issue' else [],
             'evidence_gaps': ['uncertain'] if status == 'inconclusive' else []}
    monkeypatch.setattr(provider, 'ask_model', lambda *a, **kw: (reply, '{}'))
    answer = provider.judge.judge(request, directory=tmp_path, environ={})
    assert {key: answer[key] for key in reply} == reply

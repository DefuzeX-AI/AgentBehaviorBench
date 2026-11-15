"""Cancelled model calls retain recorded stream content, never a fake response."""
import json

import pytest

from agentbench.trajectory import build, validate
from tests.trajectory_fixtures import write_json, write_jsonl

PROMPT = 'Continue until cancelled. 你好，España。'


def event(name, call='call-1', **data):
    return {'schema': 'abb.observe.event.v1', 'run_id': 'run', 'source': 'interceptor',
            'event': name, 'timestamp': '2026-01-01T00:00:01+00:00',
            'data': {'call_id': call, 'framework_span_id': call + '-span', **data}}


def request(call='call-1'):
    return event('llm_request', call, model='test/model', payload={
        'model': 'test/model', 'messages': [{'role': 'user', 'content': PROMPT}], 'stream': True})


def delta(sequence, payload, call='call-1'):
    return event('llm_delta', call, sequence=sequence, payload=payload)


def chat(text):
    return {'choices': [{'delta': {'content': text}}]}


def attempt(root, rows):
    write_json(root / 'run.json', {'run_id': 'run', 'agent_id': 'test-agent', 'status': 'interrupted'})
    write_json(root / 'invocation-one/input/request.json', {
        'schema': 'abb.invocation.v1', 'run_id': 'invocation-one', 'session_id': 'run',
        'agent_id': 'test-agent', 'framework': 'langgraph', 'input': PROMPT})
    starts = [{'schema': 'abb.observe.event.v1', 'run_id': 'run', 'source': 'framework',
               'event': 'span_start', 'timestamp': '2026-01-01T00:00:00+00:00',
               'data': {'kind': 'llm', 'span_id': row['data']['call_id'] + '-span',
                        'invocation_id': 'invocation-one', 'input': [[{'type': 'human', 'content': PROMPT}]]}}
              for row in rows if row['event'] == 'llm_request']
    write_jsonl(root / 'invocation-one/output/framework.jsonl', starts)
    write_jsonl(root / 'network.jsonl', rows)
    return root


@pytest.mark.parametrize('payloads', [
    [chat('你好，'), chat('España。')],
    [{'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
     {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': '你好，España。'}}],
    [{'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0, 'delta': '你好，'},
     {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0, 'delta': 'España。'}],
])
def test_cancelled_stream_keeps_real_partial_text_and_error(tmp_path, payloads):
    failure = event('llm_error', error_code='transport_error', error='Client disconnected.')
    failure['timestamp'] = '2026-01-01T00:00:02+00:00'
    root = attempt(tmp_path, [request(), *[delta(i, p) for i, p in enumerate(payloads, 1)], failure])
    value = validate(build(root))
    step = value['steps'][0]
    assert value['status'] == 'partial'
    assert step['status'] == 'failed'
    assert step['output_source'] == 'wire_delta'
    assert step['output']['text'] == '你好，España。'
    assert step['output']['wire_error']['error_code'] == 'transport_error'
    assert step['output']['finish_reason'] is None
    assert not step['output']['usage']
    assert step['ended_at'] == failure['timestamp']
    assert step['evidence']['stream_event_count'] == len(payloads)
    assert any('stream' in warning for warning in value['warnings'])
    assert not (root / 'invocation-one/output/result.json').exists()
    assert json.loads((root / 'run.json').read_text(encoding='utf-8'))['status'] == 'interrupted'


def test_unfinished_stream_without_terminal_error_is_not_success(tmp_path):
    root = attempt(tmp_path, [request(), delta(1, chat('unfinished'))])
    value = validate(build(root))
    assert value['status'] == 'partial'
    assert value['steps'][0]['status'] == 'incomplete'
    assert value['steps'][0]['output']['text'] == 'unfinished'
    assert value['steps'][0]['ended_at'] is None


def test_sequences_are_call_scoped_ordered_and_not_duplicated(tmp_path):
    root = attempt(tmp_path, [request(), request('call-2'), delta(2, chat('B')),
                              delta(1, chat('A')), delta(1, chat('A')),
                              delta(1, chat('other'), 'call-2')])
    steps = build(root)['steps']
    outputs = {s['evidence']['call_id']: s['output']['text'] for s in steps}
    assert outputs == {'call-1': 'AB', 'call-2': 'other'}


def test_full_response_wins_and_deltas_do_not_duplicate_content(tmp_path):
    rows = [request(), delta(1, chat('partial')), event('llm_response', status=200, payload={
        'choices': [{'message': {'content': 'final'}, 'finish_reason': 'stop'}],
        'usage': {'total_tokens': 11}})]
    value = validate(build(attempt(tmp_path, rows)))
    step = value['steps'][0]
    assert value['status'] == 'complete'
    assert step['output_source'] == 'wire'
    assert step['output']['text'] == 'final'
    assert step['output']['usage'] == {'total_tokens': 11}


def test_existing_framework_fallback_is_preserved(tmp_path):
    root = attempt(tmp_path, [request(), delta(1, chat('partial')),
                              event('llm_error', error='Client disconnected.')])
    path = root / 'invocation-one/output/framework.jsonl'
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    rows.append({'event': 'span_end', 'source': 'framework', 'timestamp': '2026-01-01T00:00:02+00:00',
                 'data': {'span_id': 'call-1-span', 'output': {
                     'generations': [[{'text': 'completed framework reply', 'message': {'content': 'completed framework reply'}}]]}}})
    write_jsonl(path, rows)
    step = build(root)['steps'][0]
    assert step['output_source'] == 'framework'
    assert step['output']['text'] == 'completed framework reply'


def test_partial_reasoning_and_tool_arguments_are_preserved_without_execution(tmp_path):
    payload = {'choices': [{'delta': {'reasoning': 'recorded reasoning', 'tool_calls': [
        {'index': 0, 'id': 'tool-1', 'function': {'name': 'lookup', 'arguments': '{"query":"中'}}]}}]}
    value = build(attempt(tmp_path, [request(), delta(1, payload), event('llm_error', error='disconnected')]))
    step = value['steps'][0]
    assert step['output']['reasoning'] == 'recorded reasoning'
    assert step['output']['tool_calls'][0]['arguments'] == '{"query":"中'
    assert step['tool_logs'][0]['execution_status'] == 'not_observed'
    assert step['tool_logs'][0]['outputs'] is None


def test_legacy_chunk_metrics_do_not_invent_text(tmp_path):
    value = build(attempt(tmp_path, [request(), event('llm_chunk', sequence=1, upstream_bytes=42),
                                    event('llm_error', error='disconnected')]))
    assert value['steps'][0]['output']['text'] is None

"""Interaction reconstruction: pagination must never split or invent a call."""
import json

import pytest

from agentbench.observe.interactions import interactions
from agentbench.observe.view_api import RunViewAPI


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def event(event_name, at, /, **data):
    return dict(event=event_name, timestamp=f'2026-09-10T07:00:{at:02d}+00:00', data=data)


def log(root, name, records):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')


@pytest.fixture
def run(tmp_path):
    write(tmp_path, 'evaluation/case.json', {'case_id': 'arbitrary-case'})
    write(tmp_path, 'evaluation/inputs/0001/input.json',
          {'case_id': 'arbitrary-case', 'input_id': 'arbitrary-input', 'payload': '请检查这一份完整数据'})
    log(tmp_path, 'evaluation/inputs/0001/framework.jsonl', [
        event('span_start', 2, span_id='span-x', kind='llm', input={'callback': 'before'}),
        event('span_end', 9, span_id='span-x', output={'callback': 'after'}),
        event('span_start', 10, span_id='tool-x', kind='tool', name='any_tool', input={'x': 1}),
        event('span_end', 11, span_id='tool-x', output={'result': 2}),
    ])
    # Intentionally unordered on disk; a call spans many raw-record pages.
    log(tmp_path, 'network.jsonl', [
        event('llm_response', 8, call_id='call-x', payload={'choices': [{'message': {
            'tool_calls': [{'id': 'tool-generated', 'function': {'name': 'any_tool', 'arguments': '{"x":1}'}}]
        }}]}, status=200),
        *[event('llm_chunk', 4, call_id='call-x', sequence=i) for i in range(105)],
        event('llm_request', 3, call_id='call-x', framework_span_id='span-x', model='any/model',
              payload={'messages': [{'role': 'user', 'content': '前缀：请检查这一份完整数据'}]}),
        event('tool_request', 7, host='unknown.example', path='/callback'),
    ])
    return tmp_path


def test_grouping_complete_payload_and_callback_evidence(run):
    page = interactions(run, {'kinds': 'chat'})
    assert page['total'] == 1
    row = page['items'][0]
    assert row['tags'] == ['chat', 'tool_call']
    assert row['chunk_count'] == 105 and row['record_count'] == 107
    assert 'payload' not in json.dumps(row)
    detail = interactions(run, {'id': row['id']})
    assert detail['link_evidence'] == 'framework_span_id'
    assert detail['context']['input_id'] == 'arbitrary-input'
    assert detail['input_matches'] == [{'path': '$["messages"][0]["content"]', 'method': 'contains_full_text'}]
    assert detail['callbacks']['output'] == {'callback': 'after'}
    assert interactions(run, {'id': row['id'], 'section': 'callbacks'})['total'] == 2
    raw = interactions(run, {'id': row['id'], 'section': 'records', 'page_size': '100', 'page': '2'})
    assert len(raw['records']) == 7 and raw['total'] == 107
    assert raw['records'][-1]['raw']['event'] == 'llm_response'
    assert interactions(run, {'kinds': 'tool'})['total'] == 1


def test_unknown_network_is_not_classified_by_domain_or_time(run):
    row = interactions(run, {'kinds': 'http'})['items'][0]
    assert row['input_id'] is None and row['link_evidence'] is None
    assert row['completeness'] == 'legacy_address_only' and row['status'] == 'unknown'
    assert interactions(run, {'q': 'tool-generated'})['total'] == 1
    assert interactions(run, {'kinds': 'chat', 'start': '2026-09-10T07:00:04Z'})['total'] == 0


def test_sdk_purpose_exact_id_and_snapshot_provenance(run):
    log(run, 'network.jsonl', [
        event('tool_request', 12, call_id='submit', host='any-host', purpose='evaluation',
              payload={'input_id': 'arbitrary-input', 'case_id': 'arbitrary-case'}),
        event('tool_response', 13, call_id='submit', status=503, payload={'error': 'retry'}),
    ])
    log(run, 'evaluation/sdk.jsonl', [dict(event('case_generated', 1, artifact='case.json'), source='sdk')])
    row = interactions(run, {'kinds': 'sdk'})['items'][0]
    assert row['status'] == 'failed' and row['link_evidence'] == 'payload_input_id'
    rows = interactions(run, {'kinds': 'case'})['items']
    case = next(r for r in rows if r['title'] == 'SDK Case')
    inp = next(r for r in rows if r['title'] == 'SDK Input')
    assert case['time_basis'] == 'recorded' and inp['time_basis'] == 'file_mtime'
    records = interactions(run, {'id': case['id'], 'section': 'records'})
    assert records['total'] == case['record_count'] == 2


def test_ambiguous_input_and_span_never_guess(run):
    write(run, 'evaluation/inputs/0002/input.json', {'input_id': 'arbitrary-input', 'payload': 'other'})
    log(run, 'evaluation/inputs/0002/framework.jsonl', [event('span_start', 2, span_id='span-x')])
    log(run, 'network.jsonl', [event('llm_request', 3, call_id='ambiguous', framework_span_id='span-x',
                                   payload={'input_id': 'arbitrary-input'})])
    assert interactions(run, {'kinds': 'chat'})['items'][0]['input_id'] is None


def test_append_partial_record_recovery_and_pagination(run):
    before = interactions(run, {})
    with (run / 'network.jsonl').open('a') as stream:
        stream.write('{"event":')
    partial = interactions(run, {})
    assert partial['warnings'] and partial['total'] == before['total']
    with (run / 'network.jsonl').open('a') as stream:
        stream.write('"new_event","data":null}\n')
    after = interactions(run, {})
    assert after['warnings'] == before['warnings'] and after['total'] == before['total'] + 1
    assert after['revision'] != before['revision']
    assert RunViewAPI(run).route(f'/api/observe/runs/{run.name}/interactions', {})['total'] == after['total']
    for args in ({'page': '0'}, {'page_size': '999'}, {'id': 'missing'}):
        with pytest.raises((ValueError, KeyError)):
            interactions(run, args)


def test_full_unicode_payload_and_symlink_boundary(tmp_path):
    body = '完整数据\u2028' * 50000
    log(tmp_path, 'network.jsonl', [event('llm_response', 1, call_id='huge', payload={'text': body})])
    row = interactions(tmp_path, {})['items'][0]
    assert interactions(tmp_path, {'id': row['id']})['response']['payload']['text'] == body
    outside = tmp_path.parent / (tmp_path.name + '-outside.json')
    outside.write_text('{"secret":"must-not-read"}')
    try:
        (tmp_path / 'evaluation').mkdir()
        (tmp_path / 'evaluation/case.json').symlink_to(outside)
        assert interactions(tmp_path, {'q': 'must-not-read'})['total'] == 0
    finally:
        outside.unlink()

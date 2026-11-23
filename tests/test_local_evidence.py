"""Local Judge projection keeps decision evidence traceable and bounded."""

import hashlib
import json

from agentbench.sdk.plugin.local.evidence import project


def test_project_keeps_ordered_tool_permission_file_events_and_sources(tmp_path, monkeypatch):
    attachments = {}

    def save(relative, content):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        attachments[relative] = {'sha256': hashlib.sha256(content.encode()).hexdigest(),
                                 'size_bytes': len(content.encode())}

    prefix = 'steps/0001'
    save(prefix + '/input.json', '{"input_id":"a","payload":"Write a file"}')
    save(prefix + '/result.json', '{"status":"succeeded","output":"Wrote it"}')
    records = [
        {'event': 'native_event', 'timestamp': '2026-01-01T00:00:00Z',
         'data': {'name': 'acp.session_update', 'payload': {'update': {
             'sessionUpdate': 'agent_thought_chunk', 'content': {'text': 'private thought'}}}}},
        {'event': 'span_start', 'timestamp': '2026-01-01T00:00:01Z',
         'data': {'name': 'acp_write_file', 'input': {'path': 'a.txt'}}},
        {'event': 'native_event', 'timestamp': '2026-01-01T00:00:02Z',
         'data': {'name': 'acp.permission', 'payload': {'outcome': 'allow_once'}}},
        {'event': 'native_event', 'timestamp': '2026-01-01T00:00:03Z',
         'data': {'name': 'acp.file_written', 'payload': {'path': 'a.txt', 'content': 'hello'}}},
        {'event': 'span_end', 'timestamp': '2026-01-01T00:00:04Z',
         'data': {'tool_status': 'succeeded', 'output': 'written'}},
    ]
    records.extend([records[0]] * 1200)
    lines = ''.join(json.dumps(item) + '\n' for item in records)
    save(prefix + '/framework.jsonl', lines)
    save(prefix + '/spans.jsonl', '')
    save(prefix + '/file-evidence.json', '{"file_evidence":{"changed":["a.txt"]}}')
    request = {'attachments': attachments, 'case': {}, 'request_id': 'test-request',
               'evidence_status': 'complete', 'unexecuted_input_ids': [], 'steps': [{
        'evidence_prefix': prefix, 'input': {'input_id': 'a', 'payload': 'Write a file'},
        'result': {'status': 'succeeded', 'output': 'Wrote it'}}]}

    payload, gaps = project(request, tmp_path)

    assert gaps == []
    assert len(lines) > 120000
    assert len(json.dumps(payload)) < 120000
    step = payload['steps'][0]
    assert [event['kind'] for event in step['events']] == [
        'span_start', 'acp.permission', 'acp.file_written', 'span_end', 'file_evidence']
    assert step['excluded_framework_events'] == {'acp.session_update.agent_thought_chunk': 1201}
    assert 'private thought' not in json.dumps(payload)
    source = step['events'][2]['source']
    assert source['path'] == prefix + '/framework.jsonl' and source['line'] == 4
    assert source['sha256'] == attachments[source['path']]['sha256']
    assert source['line_sha256'] == hashlib.sha256(lines.splitlines(keepends=True)[3].encode()).hexdigest()
    assert step['input_source']['path'] == prefix + '/input.json'
    assert step['output_source']['path'] == prefix + '/result.json'
    assert step['events'][-1]['detail']['file_evidence']['changed'] == ['a.txt']

    from agentbench.sdk.plugin.local import provider
    monkeypatch.setattr(provider, 'validate_evidence', lambda *_: None)
    monkeypatch.setattr(provider, 'judge_model', lambda _: type('Model', (), {
        'model': 'test', 'base_url': 'https://example.test/v1'})())
    seen = []
    def ask(_model, _steps, *, payload, **_kwargs):
        seen.append(payload)
        return {'status': 'pass', 'confidence': 'high', 'issues': [], 'evidence_gaps': []}, '{}'
    monkeypatch.setattr(provider, 'ask_model', ask)
    report = provider.judge.judge(request, directory=tmp_path, environ={})
    assert report['status'] == 'pass' and len(seen) == 1
    assert seen[0] == json.loads((tmp_path/'judge/local-evidence.json').read_text())


def test_oversized_decision_event_creates_gap(tmp_path, monkeypatch):
    prefix = 'steps/0001'
    records = {'event': 'span_end', 'timestamp': '2026-01-01T00:00:01Z',
               'data': {'output': 'x' * 13000}}
    relative = prefix + '/framework.jsonl'
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(records) + '\n')
    for name in ('input.json', 'result.json'):
        (path.parent / name).write_text('{}')
    attachments = {name: {'sha256': hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()}
                   for name in (relative, prefix + '/input.json', prefix + '/result.json')}
    request = {'attachments': attachments, 'case': {}, 'request_id': 'test-request',
               'evidence_status': 'complete', 'unexecuted_input_ids': [], 'steps': [{
        'evidence_prefix': prefix, 'input': {'input_id': 'a', 'payload': 'x'},
        'result': {'status': 'succeeded', 'output': 'done'}}]}

    payload, gaps = project(request, tmp_path)

    assert len(gaps) == 1 and 'Oversized span_end' in gaps[0]
    assert payload['steps'][0]['events'][0]['detail_omitted'] is True
    assert 'x' * 13000 not in json.dumps(payload)

    from agentbench.sdk.plugin.local import provider
    monkeypatch.setattr(provider, 'validate_evidence', lambda *_: None)
    def no_model(_):
        raise AssertionError('Incomplete projected evidence must not reach a model')
    monkeypatch.setattr(provider, 'judge_model', no_model)
    report = provider.judge.judge(request, directory=tmp_path, environ={})
    assert report['status'] == 'inconclusive' and report['evidence_gaps']


def test_projection_uses_verified_index_and_identifiers_not_timestamps(tmp_path):
    prefix = 'steps/0001'
    folder = tmp_path / prefix
    folder.mkdir(parents=True)
    records = [
        {'event': 'span_start', 'timestamp': '2026-01-01T00:00:01Z',
         'data': {'kind': 'tool', 'span_id': 'span-a', 'tool_call_id': 'call-a',
                  'name': 'read', 'input': {'path': 'missing.txt'}}},
        {'event': 'span_end', 'timestamp': '2026-01-01T00:00:02Z',
         'data': {'span_id': 'span-a', 'tool_call_id': 'call-a',
                  'output': 'Error: File not found'}},
    ]
    spans = [{'name': 'read', 'end_time': '2026-01-01T00:00:02Z',
              'attributes': {'gen_ai.tool.call.id': call_id, 'gen_ai.tool.call.result': output}}
             for call_id, output in [('call-a', 'Error: File not found'), ('call-b', 'unrelated')]]
    values = {'input.json': json.dumps({'input_id': 'read', 'payload': 'Read the file'}),
              'result.json': json.dumps({'status': 'succeeded', 'output': 'I read the file.'}),
              'framework.jsonl': ''.join(json.dumps(r) + '\n' for r in records),
              'spans.jsonl': ''.join(json.dumps(r) + '\n' for r in spans)}
    for name, content in values.items():
        (folder / name).write_text(content)
    # This unverified second Input must never participate in projection or pairing.
    extra = tmp_path / 'steps/0002'
    extra.mkdir()
    (extra / 'input.json').write_text('{"input_id":"unverified"}')
    (extra / 'framework.jsonl').write_text(json.dumps(records[0]))
    attachments = {prefix + '/' + name: {'sha256': hashlib.sha256(content.encode()).hexdigest(),
                                        'size_bytes': len(content.encode())}
                   for name, content in values.items()}
    request = {'attachments': attachments, 'case': {}, 'steps': [{
        'evidence_prefix': prefix, 'input': {'input_id': 'read', 'payload': 'Read the file'},
        'result': {'status': 'succeeded', 'output': 'I read the file.'}}]}
    payload, gaps = project(request, tmp_path)
    assert gaps == []
    events = payload['steps'][0]['events']
    framework, matched, unrelated = events[0], events[2], events[3]
    assert framework['tool_execution'] == matched['tool_execution']
    assert matched['tool_execution']['status'] == 'exact'
    assert unrelated['tool_execution']['status'] == 'unobserved'
    assert unrelated['tool_execution']['interaction_ids'] == []
    assert 'Error: File not found' in json.dumps(payload)
    assert payload['steps'][0]['output'] == 'I read the file.'
    assert all('0002' not in event['source']['path'] for event in events)


def test_invalid_trace_line_blocks_a_complete_projection(tmp_path):
    folder = tmp_path / 'steps/0001'
    folder.mkdir(parents=True)
    (folder / 'framework.jsonl').write_text('{invalid\n')
    (folder / 'input.json').write_text('{"input_id":"a"}')
    (folder / 'result.json').write_text('{}')
    attachments = {f'steps/0001/{name}': {'sha256': hashlib.sha256((folder / name).read_bytes()).hexdigest()}
                   for name in ('framework.jsonl', 'input.json', 'result.json')}
    _, gaps = project({'attachments': attachments, 'case': {}, 'steps': [{
        'evidence_prefix': 'steps/0001', 'input': {'input_id': 'a', 'payload': 'x'},
        'result': {'status': 'succeeded'}}]}, tmp_path)
    assert any('invalid JSON' in gap for gap in gaps)

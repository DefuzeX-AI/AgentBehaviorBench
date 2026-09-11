import json
import pytest
from agentbench.observe.view_api import RunViewAPI
from agentbench.observe.view_api import RunCatalogAPI


def test_live_span_becomes_one_finished_span(tmp_path):
    from agentbench.observe.otel.session import OtelSession
    folder = tmp_path / 'invocation-1/output'; folder.mkdir(parents=True)
    session = OtelSession(folder, 'invocation', 'run')
    api = RunViewAPI(tmp_path)
    try:
        session.record('execution_start', input='hello')
        running = api.spans()['spans']
        assert len(running) == 1 and running[0]['live']
        session.record('execution_end', output='done')
    finally:
        session.close()
    ended = api.spans()['spans']
    assert len(ended) == 1 and not ended[0]['live']
    assert ended[0]['span_id'] == running[0]['span_id']


def test_catalog_lists_siblings_refreshes_and_routes_without_escape(tmp_path):
    import os
    root = tmp_path / 'observe'; root.mkdir()
    for index, name in enumerate(('old', 'new')):
        directory = root / name; directory.mkdir()
        (directory / 'run.json').write_text(json.dumps({'agent_id': name, 'status': 'succeeded'}))
        os.utime(directory / 'run.json', (100 + index, 100 + index))
        (directory / 'network.jsonl').write_text(json.dumps({'event': name}) + '\n')
    api = RunCatalogAPI(root / 'old')
    result = api.route('/api/observe/runs', {})
    assert [run['id'] for run in result['runs']] == ['new', 'old']
    assert result['default_run'] == 'old'
    assert all(run['updated'] for run in result['runs'])
    assert api.route('/api/observe/runs/new/events', {})['events'][0]['raw']['event'] == 'new'
    assert api.route('/api/observe/runs/new/otel', {})['spans'] == []
    assert api.route('/api/observe/runs/new/evaluation', {})['inputs'] == []
    outside = tmp_path / 'outside'; outside.mkdir()
    (outside / 'run.json').write_text('{}')
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    (root / 'invalid').mkdir()
    (root / 'invalid/run.json').write_text('broken')
    assert len(api.route('/api/observe/runs', {})['runs']) == 2
    for route in ('escape/otel', '../outside/otel', 'missing/otel'):
        with pytest.raises((ValueError, OSError)):
            api.route('/api/observe/runs/' + route, {})
    (root / 'new/run.json').unlink()
    assert len(api.route('/api/observe/runs', {})['runs']) == 1


def test_bound_run_evaluation_otel_pagination_and_escape(tmp_path):
    directory = tmp_path / 'run'; directory.mkdir()
    (directory / 'run.json').write_text('{"agent_id":"company","status":"succeeded"}')
    output = directory / 'evaluation/inputs/0001'; output.mkdir(parents=True)
    (output / 'input.json').write_text('{"payload":"原文"}')
    span = {'span_id': '0123456789abcdef', 'attributes': {'abb.output_ref': 'output.json'}}
    (output / 'otel.jsonl').write_text(json.dumps({'source':'otel','event':'span','data':span})+'\n')
    body = '中文\u2028' * 100000
    (output / 'output.json').write_text(json.dumps(body))
    (directory / 'network.jsonl').write_text(''.join(json.dumps({'event': str(i)})+'\n' for i in range(101)))
    api = RunViewAPI(directory)
    assert api.evaluation()['inputs'][0]['input']['payload'] == '原文'
    assert api.route('/api/observe/runs/run/otel/0123456789abcdef/payload/output', {})['payload'] == body
    first = api.events(0)
    assert len(first['events']) == 100 and api.events(first['next'])['events'][0]['raw']['event'] == '100'
    with pytest.raises(ValueError):
        api.route('/api/observe/runs/other/otel', {})
    (output / 'output.json').unlink()
    (tmp_path / 'secret').write_text('"secret"')
    (output / 'output.json').symlink_to(tmp_path / 'secret')
    with pytest.raises(ValueError):
        api.route('/api/observe/runs/run/otel/0123456789abcdef/payload/output', {})

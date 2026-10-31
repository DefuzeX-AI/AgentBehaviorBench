"""The viewer serves trajectory.json once it exists and reports pending while the attempt runs."""
import json

from agentbench.observe.view_api import RunViewAPI
from agentbench.trajectory import SCHEMA, write
from tests.trajectory_fixtures import langgraph_attempt


def _with_status(directory, status):
    run = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
    (directory / 'run.json').write_text(json.dumps({**run, 'status': status}), encoding='utf-8')


def test_running_attempt_is_pending_until_the_file_is_written(tmp_path):
    directory = langgraph_attempt(tmp_path)
    _with_status(directory, 'running')
    route = f'/api/observe/runs/{directory.name}/trajectory'
    pending = RunViewAPI(directory).route(route, {})
    assert pending['status'] == 'pending' and pending['schema'] == SCHEMA and 'steps' not in pending
    assert 'derived_on_read' not in pending, 'a running attempt is never derived from partial records'
    assert write(directory)['status'] == 'complete'
    saved = RunViewAPI(directory).route(route, {})
    assert saved['status'] == 'complete' and len(saved['steps']) == 2 and 'derived_on_read' not in saved


def test_finished_historical_package_is_derived_on_read(tmp_path):
    directory = langgraph_attempt(tmp_path)
    _with_status(directory, 'succeeded')
    value = RunViewAPI(directory).route(f'/api/observe/runs/{directory.name}/trajectory', {})
    assert value['derived_on_read'] is True and len(value['steps']) == 2
    assert not (directory / 'trajectory.json').exists(), 'reading never writes the contract'


def test_derivation_failure_is_reported_in_the_document(tmp_path, monkeypatch):
    from agentbench.trajectory import builder
    monkeypatch.setattr(builder, 'load_index', lambda root: (_ for _ in ()).throw(ValueError('index exploded')))
    directory = langgraph_attempt(tmp_path)
    _with_status(directory, 'failed')
    value = RunViewAPI(directory).route(f'/api/observe/runs/{directory.name}/trajectory', {})
    assert value['status'] == 'failed' and 'index exploded' in value['error']

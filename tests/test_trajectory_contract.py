"""Every execute-phase package carries trajectory.json; consumers read it as evidence."""
import json

from agentbench.trajectory import SCHEMA
from tests.test_evaluation_service import project, run_one  # noqa: F401 - fixture import
from tests.test_sdk_defaults import inprocess_worker_permissions  # noqa: F401 - autouse fixture
from tests.test_sdk_execution import fake_services, make_runner, source_agent


def test_execution_writes_trajectory_and_records_its_status(tmp_path):
    agent = source_agent(tmp_path)
    services, calls = fake_services()
    runner = make_runner(tmp_path, services)
    case, = runner.prepare_cases(agent)
    assert runner.run_case(agent, case).passed
    status = json.loads((runner.directory / 'run.json').read_text(encoding='utf-8'))
    assert status['trajectory']['path'] == 'trajectory.json'
    assert status['trajectory']['status'] in ('complete', 'partial')
    saved = json.loads((runner.directory / 'trajectory.json').read_text(encoding='utf-8'))
    assert saved['schema'] == SCHEMA and saved['agent_id'] == agent.agent_id
    assert saved['status'] == status['trajectory']['status']


def test_derivation_failure_is_recorded_without_changing_the_outcome(tmp_path, monkeypatch):
    from agentbench.trajectory import builder
    monkeypatch.setattr(builder, 'load_index', lambda root: (_ for _ in ()).throw(RuntimeError('index exploded')))
    agent = source_agent(tmp_path)
    services, _ = fake_services()
    runner = make_runner(tmp_path, services)
    case, = runner.prepare_cases(agent)
    assert runner.run_case(agent, case).passed
    status = json.loads((runner.directory / 'run.json').read_text(encoding='utf-8'))
    assert status['status'] == 'succeeded'
    assert status['trajectory']['status'] == 'failed'
    saved = json.loads((runner.directory / 'trajectory.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'failed' and 'index exploded' in saved['error']


def test_judge_request_attaches_trajectory_and_evidence_api_returns_it(project):
    service, agent, _ = project
    result = run_one(service)
    assert result['suite']['counts']['completed'] == 1
    suite, run = result['directory'], result['runs'][0]['id']
    evidence = service.evidence(suite, run)
    assert evidence['schema'] == 'abb.evaluation.evidence.v2'
    assert 'trajectory.json' in evidence['request']['attachments']
    assert evidence['trajectory']['schema'] == SCHEMA and 'derived_on_read' not in evidence['trajectory']
    assert evidence['spans']['statuses']
    attached = service.attachment(suite, run, 'trajectory.json')
    assert attached['content']


def _host_after_run(project, monkeypatch, write):
    import agentbench.trajectory as trajectory
    monkeypatch.setattr(trajectory, 'write', write)
    service, _, _ = project
    result = run_one(service)
    suite, run = result['directory'], result['runs'][0]['id']
    api, _ = service._run(suite, run)
    return result, api.read('run.json'), api.directory


def test_missing_trajectory_is_reported_without_failing_the_execution(project, monkeypatch):
    result, host, directory = _host_after_run(project, monkeypatch,
                                              lambda directory, **kw: {'status': 'skipped', 'path': 'trajectory.json'})
    assert not (directory / 'trajectory.json').exists()
    assert result['suite']['counts']['completed'] == 1
    assert host['status'] == 'succeeded' and host.get('validation') != 'failed'
    assert host['trajectory']['status'] == 'failed' and host['trajectory']['error_type'] == 'FileNotFoundError'


def test_unreadable_trajectory_is_reported_without_failing_the_execution(project, monkeypatch):
    def corrupt(directory, **kw):
        (directory / 'trajectory.json').write_text('{not json', encoding='utf-8')
        return {'status': 'complete', 'path': 'trajectory.json'}
    result, host, _ = _host_after_run(project, monkeypatch, corrupt)
    assert result['suite']['counts']['completed'] == 1
    assert host['status'] == 'succeeded' and host.get('validation') != 'failed'
    assert host['trajectory']['status'] == 'failed' and host['trajectory']['error_type'] == 'JSONDecodeError'

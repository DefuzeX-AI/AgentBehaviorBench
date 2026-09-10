import json
from types import SimpleNamespace

import pytest

from agentbench.cli.execution import run_benchmark_once
from agentbench.cli.result_export import start_result_log
from agentbench.harness import BenchmarkProgress
from agentbench.observe.view_api import SuiteRunCatalogAPI
from tests.test_cli import FakeSuiteRunner


def test_cli_defaults_to_saved_live_viewer_and_supports_no_view(monkeypatch):
    from agentbench.cli.main import cli
    received = []
    monkeypatch.setattr('agentbench.cli.features.run.run', lambda **kw: received.append(kw) or 0)
    assert cli(['run']) == 0
    assert received[-1] == {'output_path': 'results/result.json'}
    assert cli(['run', '--no-view']) == 0
    assert received[-1] == {'output_path': 'results/result.json', 'viewer_starter': None}


def test_suite_discovers_live_artifacts_before_completion(tmp_path):
    writer = start_result_log(tmp_path / 'result.json', suite_id='s', selected_agent_ids=('a',))
    api = SuiteRunCatalogAPI(writer.path)
    assert api.route('/api/observe/runs', {})['runs'] == []
    directory = tmp_path / 'raw/run1'
    directory.mkdir(parents=True)
    metadata = {'schema': 'abb.evaluate.run.v1', 'run_id': 'run1', 'agent_id': 'a', 'status': 'running'}
    (directory / 'run.json').write_text(json.dumps(metadata))
    writer.append_progress(BenchmarkProgress('benchmark_execution', 'started', 'a',
                                             artifact_directory=str(directory)))
    assert api.route('/api/observe/runs', {})['runs'][0]['status'] == 'running'
    assert api.route('/api/observe/runs/run1/evaluation', {})['judge'] is None
    folder = directory / 'evaluation/inputs/0001'
    folder.mkdir(parents=True)
    span = {'span_id': '0123456789abcdef', 'live': True, 'attributes': {}}
    (folder / 'otel-live.jsonl').write_text(json.dumps({'data': span}) + '\n')
    assert api.route('/api/observe/runs/run1/otel', {})['spans'][0]['live']
    (directory / 'run.json').write_text(json.dumps({**metadata, 'status': 'failed'}))
    assert api.route('/api/observe/runs', {})['runs'][0]['status'] == 'failed'
    with pytest.raises(ValueError):
        api.route('/api/observe/runs/unregistered/otel', {})
    (directory / 'run.json').write_text(json.dumps({**metadata, 'agent_id': 'other'}))
    assert api.route('/api/observe/runs', {})['runs'] == []


def test_viewer_and_progress_log_exist_before_runner_starts(tmp_path, ready_agents):
    output = []
    started = []
    def viewer(path):
        started.append(path)
        return SimpleNamespace(url='http://127.0.0.1:12345')
    class Runner(FakeSuiteRunner):
        def run(self, agents, **kwargs):
            assert started
            assert any(line.startswith('View: http://') for line in output)
            kwargs['on_progress'](BenchmarkProgress('agent_start', 'started', agents[0].agent_id))
            assert json.loads(started[0].read_text())[-1]['event'] == 'progress'
            return super().run(agents, **kwargs)
    result = run_benchmark_once(ready_agents, runner=Runner(), output_path=tmp_path / 'result.json',
                                output_fn=output.append, viewer_starter=viewer)
    assert result.exit_code == 0
    assert json.loads(started[0].read_text())[-1]['event'] == 'suite_completed'


@pytest.mark.parametrize('error', [KeyboardInterrupt(), RuntimeError('controlled failure')])
def test_interruption_and_unexpected_failure_stop_server(tmp_path, ready_agents, error):
    stopped = []
    viewer = SimpleNamespace(url='http://127.0.0.1:12345', stop=lambda: stopped.append(True))
    def execute():
        return run_benchmark_once(ready_agents, runner=FakeSuiteRunner(error=error),
            output_path=tmp_path / 'result.json', output_fn=lambda _: None,
            viewer_starter=lambda _: viewer)
    if isinstance(error, KeyboardInterrupt):
        assert execute().exit_code == 130
    else:
        with pytest.raises(RuntimeError, match='controlled failure'):
            execute()
    assert stopped == [True]
    assert json.loads(next(tmp_path.glob('result-*.json')).read_text())[-1]['event'] == 'suite_failed'


def test_viewer_bind_failure_preserves_benchmark_execution(tmp_path, ready_agents):
    def unavailable(_):
        raise OSError('No available port')
    result = run_benchmark_once(ready_agents, runner=FakeSuiteRunner(),
        output_path=tmp_path / 'result.json', output_fn=lambda _: None, viewer_starter=unavailable)
    assert result.exit_code == 0 and result.viewer is None
    assert result.result_log.path.is_file()


def test_kuma_announces_artifacts_before_build_and_retains_failure(tmp_path, monkeypatch):
    from agentbench.sdk.kuma_runtime import service
    from agentbench.sdk.kuma_runtime.benchmark import KumaContainerRunner
    events = []
    def failed_build(*_):
        assert events and events[0].artifact_directory
        assert json.loads((tmp_path / 'result.json').read_text())['status'] == 'running'
        raise RuntimeError('controlled build failure')
    # Read the announced metadata while the build has not started yet.
    def progress(event):
        from pathlib import Path
        events.append(event)
        (tmp_path / 'result.json').write_text((Path(event.artifact_directory) / 'run.json').read_text())
    monkeypatch.setattr(service, 'evaluation_agent', failed_build)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline'}, options={'output': tmp_path / 'raw'})
    monkeypatch.setattr(runner, 'validate_sdk', lambda _: 'official-container')
    with pytest.raises(RuntimeError, match='controlled build failure'):
        runner.run(SimpleNamespace(agent_id='a'), on_progress=progress)
    from pathlib import Path
    assert json.loads((Path(events[0].artifact_directory) / 'run.json').read_text())['status'] == 'failed'

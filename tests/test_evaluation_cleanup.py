"""Host cleanup remains reliable when evidence persistence fails."""

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.runtime.contracts.execution import DockerCleanupError, RunCancelled, RuntimeLimits
from agentbench.sdk.integration import execution
from agentbench.sdk.plugin.kuma import diagnostics, service


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    root = tmp_path / 'agent'
    root.mkdir()
    (root / 'agent.toml').write_text(
        'agent_id = "fixture"\n[evaluation.workspace]\n'
        'path = "/home/agent/workspace"\ninitial_state = "empty"\n')
    agent = SimpleNamespace(path=root, agent_id='fixture')
    state = SimpleNamespace(events=[], failure=None, primary=None, close_errors={},
                            workspace_error=None, start_error=None, directory=None, workspace=None)
    artifact_save = execution.Artifacts.save
    temporary_directory = execution.tempfile.TemporaryDirectory
    collect_artifacts = diagnostics.collect_artifacts

    @contextmanager
    def staged(agent, **kwargs):
        yield agent

    class Files(execution.Artifacts):
        def save(self, relative, value):
            final_status = relative == 'run.json' and value['status'] != 'running'
            if relative in ('diagnostics.json', 'agent-diagnostics.json') or final_status:
                state.events.append(relative)
                if state.failure == relative:
                    raise OSError('cannot save ' + relative)
            return artifact_save(self, relative, value)

    class Workspace:
        def __init__(self, **kwargs):
            self.temporary = temporary_directory(**kwargs)
            self.name = self.temporary.name
            state.workspace = Path(self.name)

        def cleanup(self):
            state.events.append('cleanup workspace')
            self.temporary.cleanup()
            if state.workspace_error is not None:
                raise state.workspace_error

    class Session:
        def __init__(self, label):
            self.label = label
            self.stdout, self.stderr = label + ' stdout', label + ' stderr'

        def trace_checkpoint(self):
            return 'checkpoint'

        def validate_trace(self, checkpoint):
            assert checkpoint == 'checkpoint'

        def wait(self, **kwargs):
            if state.primary is not None:
                raise state.primary
            return 0

        def close(self):
            state.events.append('close ' + self.label)
            if self.label in state.close_errors:
                raise state.close_errors[self.label]

    def runtime(**kwargs):
        label = 'agent' if kwargs['run_id'].endswith('-agent') else 'controller'
        def start(*args, **options):
            if label == 'controller' and state.start_error is not None:
                raise state.start_error
            return Session(label)
        return SimpleNamespace(start=start)

    def collect(*args, **kwargs):
        state.events.append('collect artifacts')
        if state.failure == 'collect artifacts':
            raise OSError('cannot collect artifacts')
        return collect_artifacts(*args, **kwargs)

    def run(**kwargs):
        return service.evaluate(agent, output=tmp_path / 'output', environ={},
            require_credentials=False, on_artifacts_ready=lambda path: setattr(state, 'directory', path),
            runtime_services=SimpleNamespace(create_docker_runtime=runtime, limits=RuntimeLimits()),
            **kwargs)

    monkeypatch.setattr(service, 'evaluation_agent', staged)
    monkeypatch.setattr(execution, 'Artifacts', Files)
    monkeypatch.setattr(execution.tempfile, 'TemporaryDirectory', Workspace)
    monkeypatch.setattr(diagnostics, 'collect_artifacts', collect)
    state.run = run
    state.status = lambda: json.loads((state.directory / 'run.json').read_text())
    return state


def assert_released(evaluation):
    assert evaluation.events.count('close controller') == 1
    assert evaluation.events.count('close agent') == 1
    assert evaluation.events.count('cleanup workspace') == 1
    assert not evaluation.workspace.exists()


@pytest.mark.parametrize('failure', ['diagnostics.json', 'agent-diagnostics.json',
                                    'collect artifacts', 'run.json'])
def test_persistence_failure_releases_resources_and_fails_the_run(evaluation, failure):
    evaluation.failure = failure
    with pytest.raises(OSError, match='cannot'):
        evaluation.run()
    assert_released(evaluation)
    if failure != 'run.json':
        status = evaluation.status()
        assert status['status'] == 'failed'
        assert status['cleanup_status'] == 'succeeded'
        assert status['error_type'] == 'OSError'
    # Failure to write one stream must not skip the other stream's evidence.
    if failure == 'diagnostics.json':
        saved = json.loads((evaluation.directory / 'agent-diagnostics.json').read_text())
        assert saved['stdout'] == 'agent stdout'


@pytest.mark.parametrize('failure', ['diagnostics.json', 'agent-diagnostics.json',
                                    'collect artifacts', 'run.json'])
@pytest.mark.parametrize('error_class', [RuntimeError, RunCancelled])
def test_persistence_failure_preserves_the_original_execution_error(evaluation, failure, error_class):
    evaluation.failure = failure
    evaluation.primary = error_class('original execution failure')
    with pytest.raises(error_class, match='original execution failure') as caught:
        evaluation.run()
    assert caught.value is evaluation.primary
    assert_released(evaluation)
    if failure != 'run.json':
        status = evaluation.status()
        assert status['error'] == 'original execution failure'
        assert status['cleanup_status'] == 'succeeded'
        assert status['status'] == ('cancelled' if error_class is RunCancelled else 'failed')
    if failure != 'collect artifacts':
        assert caught.value.artifacts['directory'] == str(evaluation.directory.resolve())


@pytest.mark.parametrize('failure', [None, 'diagnostics.json', 'collect artifacts', 'run.json'])
def test_container_cleanup_failure_stays_fatal_despite_other_failures(evaluation, failure):
    evaluation.failure = failure
    evaluation.primary = RunCancelled('original cancellation')
    cleanup_error = DockerCleanupError('controller still exists')
    evaluation.close_errors = {
        'controller': cleanup_error,
        'agent': DockerCleanupError('agent still exists'),
    }
    with pytest.raises(DockerCleanupError, match='controller still exists') as caught:
        evaluation.run()
    assert caught.value is cleanup_error
    assert_released(evaluation)
    if failure != 'run.json':
        status = evaluation.status()
        assert status['status'] == 'failed'
        assert status['cleanup_status'] == 'failed'
        assert status['cleanup_error_type'] == 'DockerCleanupError'
        assert status['error'] == 'original cancellation'


def test_workspace_cleanup_failure_is_recorded_before_final_status(evaluation):
    evaluation.workspace_error = OSError('workspace cleanup failed')
    with pytest.raises(OSError, match='workspace cleanup failed'):
        evaluation.run()
    assert_released(evaluation)
    status = evaluation.status()
    assert status['status'] == 'failed'
    assert status['cleanup_status'] == 'failed'
    assert status['cleanup_error'] == 'workspace cleanup failed'


def test_startup_cleanup_failure_remains_fatal_when_workspace_cleanup_also_fails(evaluation):
    evaluation.start_error = DockerCleanupError('controller startup cleanup failed')
    evaluation.workspace_error = OSError('workspace cleanup failed')
    with pytest.raises(DockerCleanupError, match='controller startup cleanup failed') as caught:
        evaluation.run()
    assert caught.value is evaluation.start_error
    assert evaluation.events.count('close controller') == 0
    assert evaluation.events.count('close agent') == 1
    assert evaluation.events.count('cleanup workspace') == 1
    assert not evaluation.workspace.exists()
    status = evaluation.status()
    assert status['status'] == status['cleanup_status'] == 'failed'
    assert status['cleanup_error_type'] == 'DockerCleanupError'
    assert status['cleanup_error'] == str(caught.value)


def test_later_docker_cleanup_failure_takes_priority_over_ordinary_close_error(evaluation):
    cleanup_error = DockerCleanupError('agent still exists')
    evaluation.close_errors = {'controller': OSError('controller close failed'), 'agent': cleanup_error}
    with pytest.raises(DockerCleanupError, match='agent still exists') as caught:
        evaluation.run()
    assert caught.value is cleanup_error
    assert_released(evaluation)
    status = evaluation.status()
    assert status['status'] == status['cleanup_status'] == 'failed'
    assert status['cleanup_error_type'] == 'DockerCleanupError'
    assert status['cleanup_error'] == str(caught.value)


def test_success_preserves_both_diagnostics_and_cleans_the_workspace(evaluation):
    assert evaluation.run() == evaluation.directory
    assert_released(evaluation)
    status = evaluation.status()
    assert status['status'] == status['cleanup_status'] == 'succeeded'
    assert status['host_trace_validation'] == 'succeeded'
    for path, label in [('diagnostics.json', 'controller'), ('agent-diagnostics.json', 'agent')]:
        saved = json.loads((evaluation.directory / path).read_text())
        assert saved['stdout'] == label + ' stdout'
        assert saved['stderr'] == label + ' stderr'

"""Recovery cancellation exists before dispatch and follows the Viewer's lifetime."""

import threading
from types import SimpleNamespace

import pytest

from agentbench.cli import execution, viewer
from agentbench.cli.sessions import configuration, control, fresh, recovery
from agentbench.harness import SuiteRunner
from agentbench.harness.session import SuiteStore, read_snapshot
from agentbench.runtime.contracts.execution import RunCancelled, RunControl
from tests.test_suite_concurrency import Factory, agents
from tests.test_suite_resume import make_agent, make_case, runner_for


@pytest.fixture(autouse=True)
def isolated_reference_index(tmp_path, monkeypatch):
    monkeypatch.setattr(fresh, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(recovery, 'PROJECT_ROOT', tmp_path)


def saved_suite(tmp_path):
    agent = make_agent(tmp_path, 1)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_lifecycle', [agent]) as store:
        store.retain_case(agent.agent_id, make_case(tmp_path / 'cases', 0))
        return store.path


def test_pre_cancelled_signal_never_opens_suite_resources():
    factory = Factory()
    runner = SuiteRunner(runner_factory=factory)
    signal = RunControl()
    signal.cancel()
    with pytest.raises(RunCancelled):
        runner.run(agents(), run_control=signal)
    assert factory.sessions == factory.prepared == factory.created == []
    assert runner._active_control is None
    assert runner.run(agents()).passed  # The cancelled command does not poison a new run.


def test_close_between_runner_hook_and_run_prevents_case_execution(tmp_path, monkeypatch):
    path = saved_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(recovery, 'build_saved_runner', lambda *args, **kwargs: runner)
    entered, continue_start = threading.Event(), threading.Event()
    coordinator = control.SuiteControl(path, {})
    original = coordinator._set_active

    def before_run(identifier, active):
        original(identifier, active)
        if active is not None:
            entered.set()
            assert continue_start.wait(3)

    monkeypatch.setattr(coordinator, '_set_active', before_run)
    closer = None
    try:
        coordinator.submit({'command_id': 'race', 'action': 'resume'}, coordinator.token)
        assert entered.wait(3)
        assert runner._active_control is None  # Exact previously unsafe startup window.
        closer = threading.Thread(target=coordinator.close)
        closer.start()
        assert coordinator._signals['race'].wait(2)
        continue_start.set()
        closer.join(timeout=3)
        assert not closer.is_alive()
        assert factory.executed == factory.generated == factory.recovered == []
        assert coordinator.commands[0]['status'] == 'rejected'
        snapshot = read_snapshot(path.parent)
        assert snapshot['commands'][-1]['status'] == 'rejected'
        assert snapshot['jobs'][0]['cases'][0]['attempts'] == []
    finally:
        continue_start.set()
        coordinator.close()
        if closer is not None:
            closer.join(timeout=3)


def test_close_while_waiting_for_writer_lock_never_dispatches(tmp_path, monkeypatch):
    path = saved_suite(tmp_path)
    started = threading.Event()
    actual = control.execute_recovery

    def record(*args, **kwargs):
        started.set()
        return actual(*args, **kwargs)

    monkeypatch.setattr(control, 'execute_recovery', record)
    coordinator = control.SuiteControl(path, {})
    with SuiteStore.open(path.parent):
        coordinator.submit({'command_id': 'queued', 'action': 'resume'}, coordinator.token)
        assert started.wait(2)
        coordinator.close()
    assert not coordinator._thread.is_alive()
    assert coordinator.commands[0]['status'] == 'rejected'
    assert coordinator._signals['queued'].cancelled
    assert read_snapshot(path.parent)['revision'] == 2


def test_no_view_run_does_not_register_background_controller(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, 1)
    runner = SuiteRunner(runner_factory=Factory())
    monkeypatch.setattr(configuration, 'runner_configuration', lambda value: {})
    def unexpected(*args, **kwargs):
        pytest.fail('A no-view run must not create a recovery controller')
    monkeypatch.setattr(control, 'register_control', unexpected)
    outcome = execution.run_benchmark_once((agent,), runner=runner, output_path=tmp_path / 'result.json',
                                           output_fn=lambda line: None, viewer_starter=None)
    assert outcome.result.passed and outcome.viewer is None
    assert control.get_control(outcome.result_log.path) is None
    from agentbench.harness.session.references import collect_suite_references
    assert [item.directory for item in collect_suite_references(tmp_path)] == [outcome.result_log.store.directory]


def test_failed_viewer_start_closes_registered_controller_before_run(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, 1)
    runner = SuiteRunner(runner_factory=Factory())
    monkeypatch.setattr(configuration, 'runner_configuration', lambda value: {})
    registered = []
    original = control.register_control
    def register(*args):
        result = original(*args)
        registered.append(result)
        return result
    monkeypatch.setattr(control, 'register_control', register)
    def unavailable(path):
        raise OSError('No viewer assets')
    outcome = execution.run_benchmark_once((agent,), runner=runner, output_path=tmp_path / 'result.json',
                                           output_fn=lambda line: None, viewer_starter=unavailable)
    assert outcome.result.passed and outcome.viewer is None
    assert len(registered) == 1 and not registered[0]._thread.is_alive()
    assert control.get_control(outcome.result_log.path) is None


def test_running_viewer_stop_releases_its_controller_and_http_resources(tmp_path, monkeypatch):
    path = saved_suite(tmp_path)
    coordinator = control.register_control(path, {})
    calls = []
    server = SimpleNamespace(server_port=9999, serve_forever=lambda: None,
                             shutdown=lambda: calls.append('shutdown'),
                             server_close=lambda: calls.append('close'))
    monkeypatch.setattr(viewer, 'require_viewer_assets', lambda: None)
    monkeypatch.setattr(viewer, 'create_viewer_server', lambda *args, **kwargs: server)
    running = viewer.start_viewer_server(path)
    running.stop()
    assert calls == ['shutdown', 'close']
    assert control.get_control(path) is None and not coordinator._thread.is_alive()


def test_session_quit_closes_control_even_for_injected_viewer(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, 1)
    runner = SuiteRunner(runner_factory=Factory())
    monkeypatch.setattr(configuration, 'runner_configuration', lambda value: {})
    stopped = []
    injected = SimpleNamespace(url='http://127.0.0.1/', stop=lambda: stopped.append(True))
    outcome = execution.run_benchmark_session((agent,), runner=runner, output_path=tmp_path / 'result.json',
        output_fn=lambda line: None, viewer_starter=lambda path: injected, input_fn=lambda prompt: 'q')
    assert stopped == [True]
    assert control.get_control(outcome.result_log.path) is None


@pytest.mark.parametrize('canonical', [False, True])
def test_view_uses_saved_configuration_without_validating_execution_environment(tmp_path, monkeypatch, canonical):
    from agentbench.cli import environment
    from agentbench.cli.features import view
    path = saved_suite(tmp_path) if canonical else tmp_path / 'legacy.json'
    if not canonical:
        path.write_text('{}', encoding='utf-8')
    loaded, served, registered, closed = [], [], [], []
    monkeypatch.setenv('ABB_MAX_PARALLEL_CASES', 'invalid-for-a-new-run')
    monkeypatch.setattr(environment, 'load_project_environment', lambda value: loaded.append(value))
    def register(path, environ):
        registered.append((path, environ))
        return SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(control, 'register_control', register)
    monkeypatch.setattr(view, 'serve_result_log', lambda *args, **kwargs: served.append(args[0]))
    assert view.execute(SimpleNamespace(result_log=str(path), host='127.0.0.1', port=0)) == 0
    assert served == [str(path)]
    assert len(loaded) == len(registered) == len(closed) == int(canonical)
    if canonical:
        assert registered[0][1]['ABB_MAX_PARALLEL_CASES'] == 'invalid-for-a-new-run'


def test_failed_fresh_suite_index_closes_writer_before_any_dispatch(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, 1)
    factory = Factory()
    runner = SuiteRunner(runner_factory=factory)
    monkeypatch.setattr(configuration, 'runner_configuration', lambda value: {})
    def failed_index(*args, **kwargs):
        raise OSError('Cannot publish Suite reference')
    monkeypatch.setattr(fresh, 'register_suite_reference', failed_index)
    with pytest.raises(OSError, match='Cannot publish Suite reference'):
        execution.run_benchmark_once((agent,), runner=runner, output_path=tmp_path / 'result.json',
                                    output_fn=lambda line: None, viewer_starter=None)
    assert factory.sessions == factory.prepared == factory.created == []
    suite_directory = next((tmp_path / 'suites').iterdir())
    with SuiteStore.open(suite_directory) as reopened:
        assert reopened.snapshot()['jobs'][0]['cases'][0]['attempts'] == []

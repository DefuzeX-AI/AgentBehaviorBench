"""Single saved Case selection, fresh execution/judging, and durable request identity."""

import threading
from types import SimpleNamespace

import pytest

from agentbench.cli.sessions import control, recovery, reuse, reuse_target, reuse_command
from agentbench.harness import SuiteRunner
from agentbench.harness.session import SuiteStore, read_snapshot
from tests.test_suite_reuse import original_suite
from tests.test_suite_resume import runner_for
from tests.test_judge_queue import DeferredFactory


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    for module in (reuse, recovery, reuse_target):
        monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)


def test_selected_nonzero_case_runs_agent_and_judge_again_without_generation(tmp_path):
    source, agents = original_suite(tmp_path, agents=2, cases=3)
    before = (source / 'events.json').read_bytes()
    executed, judged = [], []
    factory = DeferredFactory(tmp_path, lambda index, _: executed.append(index), lambda index, _: judged.append(index))
    runner = SuiteRunner(runner_factory=factory)
    with SuiteStore.open(source) as store:
        original = store.prepared_case(agents[1].agent_id, 2)
        unrelated = store.prepared_case(agents[0].agent_id, 0)
    unrelated.artifact_path.unlink()  # Single-Case reuse must not depend on other artifacts.
    result = reuse.execute_reuse(source, environ={}, selection={('agent-1', 2)}, runner=runner)
    assert executed == judged == [0]
    assert factory.prepared == []
    assert (source / 'events.json').read_bytes() == before
    snapshot = read_snapshot(result.directory)
    assert snapshot['counts']['planned'] == snapshot['counts']['completed'] == snapshot['counts']['judge_received'] == 1
    case = snapshot['jobs'][0]['cases'][0]
    assert case['case_id'] == original.case_id
    assert case['origin']['agent_id'] == 'agent-1' and case['origin']['case_index'] == 2
    with SuiteStore.open(result.directory) as store:
        saved = store.prepared_case('agent-1', 0)
    assert saved.artifact_path.read_bytes() == original.artifact_path.read_bytes()
    assert saved.artifact_sha256 == original.artifact_sha256


def test_live_suite_writer_remains_open_while_selected_case_finishes_reuse(tmp_path):
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    with SuiteStore.open(source) as live:
        live.append({'event': 'case_started', 'agent_id': 'agent-0', 'case_index': 1,
                     'attempt_id': 'still-running', 'attempt_number': 2})
        before = (source / 'events.json').read_bytes()
        revision = live.snapshot()['revision']
        execution = reuse.execute_reuse(source, environ={}, selection={('agent-0', 1)}, runner=runner)
        assert len(factory.executed) == 1 and factory.generated == []
        assert (source / 'events.json').read_bytes() == before
        case = read_snapshot(execution.directory)['jobs'][0]['cases'][0]
        assert case['execution_status'] == 'completed'
        assert case['origin']['revision'] == revision
        live.append({'event': 'progress', 'agent_id': 'agent-0', 'case_index': 1})
        assert live.snapshot()['jobs'][0]['cases'][1]['execution_status'] == 'retrying'


@pytest.mark.parametrize('selection', [set(), {('missing', 0)}, {('agent-0', 99)}])
def test_invalid_selection_creates_no_suite(tmp_path, selection):
    source, _ = original_suite(tmp_path)
    runner, _ = runner_for(tmp_path)
    with pytest.raises(ValueError, match='selection'):
        reuse.prepare_reuse(source, environ={}, selection=selection, runner=runner, suite_id='suite_bad')
    assert not (source.parent / 'suite_bad').exists()


def test_case_id_artifact_id_and_paths_resolve_exact_case(tmp_path):
    source, _ = original_suite(tmp_path)
    artifact = tmp_path / 'observe' / 'run-123'
    with SuiteStore.open(source) as store:
        case = store.prepared_case('agent-0', 1)
        store.append({'event': 'progress', 'agent_id': 'agent-0', 'case_index': 1,
                      'attempt_id': 'initial-1', 'artifact_run_id': artifact.name, 'artifact_directory': str(artifact)})
    for value in ('case-1', 'run-123', artifact, artifact / 'evaluation' / 'judge' / 'report.json', case.artifact_path):
        target = reuse_target.resolve_reuse_target(value, source.parent)
        assert target.directory == source
        assert target.selection == {('agent-0', 1)}
    assert reuse_target.resolve_reuse_target(source).selection is None
    assert reuse_target.resolve_reuse_target('suite_original', source.parent, agent_id='agent-0', case_number=2).selection == {('agent-0', 1)}


def test_ambiguous_identity_lists_explicit_commands_and_external_index_is_searchable(tmp_path):
    source, _ = original_suite(tmp_path)
    runner, _ = runner_for(tmp_path)
    reuse.prepare_reuse(source, environ={}, runner=runner, selection={('agent-0', 1)}, root=tmp_path / 'external')
    with pytest.raises(ValueError, match='multiple saved') as error:
        reuse_target.resolve_reuse_target('case-1')
    assert '--agent agent-0 --case 2' in str(error.value)
    assert '--agent agent-0 --case 1' in str(error.value)


@pytest.mark.parametrize('kwargs', [{'agent_id': 'agent-0'}, {'case_number': 2}, {'agent_id': 'agent-0', 'case_number': 0}])
def test_cli_selection_options_are_validated(tmp_path, kwargs):
    source, _ = original_suite(tmp_path)
    with pytest.raises(ValueError):
        reuse_target.resolve_reuse_target(source, **kwargs)


def test_missing_identity_fails_before_building_runner(tmp_path):
    with pytest.raises(ValueError, match='No saved'):
        reuse_target.resolve_reuse_target('nonexistent', tmp_path)


def test_cli_case_id_dispatches_single_reuse(tmp_path, monkeypatch, capsys):
    from agentbench.cli.main import build_parser
    from agentbench.cli.features import reuse as feature
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: runner)
    monkeypatch.setattr(feature, 'load_project_environment', lambda *_: None)
    monkeypatch.setattr(feature, 'execution_environment_snapshot', lambda: SimpleNamespace(environ={}))
    monkeypatch.setattr(feature, 'project_root', lambda: tmp_path)
    args = build_parser().parse_args(['reuse', 'case-1', '--suite-root', str(source.parent)])
    assert feature.execute(args) == 0
    assert [(index, case_id) for index, case_id, _ in factory.executed] == [(0, 'case-1')]
    assert 'agentbench view' in capsys.readouterr().out


def test_same_viewer_request_survives_controller_restart_without_second_execution(tmp_path, monkeypatch):
    source, _ = original_suite(tmp_path)
    before = (source / 'events.json').read_bytes()
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: runner)
    destination = reuse_command.execute_reuse_command(source, command_id='same', selection={('agent-0', 1)}, environ={})
    assert reuse_command.execute_reuse_command(source, command_id='same', selection={('agent-0', 1)}, environ={}) == destination
    assert len(factory.executed) == 1 and factory.generated == []
    assert (source / 'events.json').read_bytes() == before
    with pytest.raises(ValueError, match='does not match'):
        reuse_command.execute_reuse_command(source, command_id='same', selection={('agent-0', 0)}, environ={})


def test_viewer_completed_case_reuse_is_queued_once_and_links_to_same_viewer(tmp_path, monkeypatch):
    from agentbench.cli import viewer
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: runner)
    stopped, completed = threading.Event(), threading.Event()
    monkeypatch.setattr(viewer, 'start_viewer_server', lambda *args, **kwargs:
                        SimpleNamespace(url='http://127.0.0.1:1234/', stop=stopped.set))
    controller = control.SuiteControl(source / 'events.json', {})
    original = controller._set_status
    def status(identifier, value, error=None):
        original(identifier, value, error)
        if value in {'completed', 'rejected'}:
            completed.set()
    monkeypatch.setattr(controller, '_set_status', status)
    payload = {'command_id': 'browser', 'action': 'reuse', 'agent_id': 'agent-0', 'case_index': 1}
    try:
        controller.submit(payload, controller.token)
        controller.submit(payload, controller.token)
        assert completed.wait(5)
        command = controller.submit(payload, controller.token)
        assert command['status'] == 'completed', command
        assert command['result_url'] == f'/suite/{command["suite_id"]}/'
        assert command['result_path'].endswith('/events.json')
        assert len(factory.executed) == 1
    finally:
        controller.close()
    assert not stopped.is_set()  # Reuse no longer creates a child HTTP server.


def test_viewer_reuses_running_case_despite_source_progress_and_writer_lock(tmp_path, monkeypatch):
    from agentbench.cli import viewer
    source, _ = original_suite(tmp_path)
    runner, factory = runner_for(tmp_path)
    monkeypatch.setattr(reuse, 'build_saved_runner', lambda *_: runner)
    monkeypatch.setattr(viewer, 'start_viewer_server', lambda *args, **kwargs:
                        SimpleNamespace(url='http://127.0.0.1:1234/', stop=lambda: None))
    coordinator = control.SuiteControl(source / 'events.json', {})
    finished = threading.Event()
    original = coordinator._set_status
    def status(identifier, value, error=None):
        original(identifier, value, error)
        if value in {'completed', 'rejected'}:
            finished.set()
    monkeypatch.setattr(coordinator, '_set_status', status)
    try:
        with SuiteStore.open(source) as live:
            stale_revision = live.snapshot()['revision']
            live.append({'event': 'case_started', 'agent_id': 'agent-0', 'case_index': 0,
                         'attempt_id': 'active', 'attempt_number': 2})
            payload = {'command_id': 'during-run', 'action': 'reuse', 'agent_id': 'agent-0',
                       'case_index': 0, 'expected_revision': stale_revision}
            coordinator.submit(payload, coordinator.token)
            assert finished.wait(5), 'Reuse waited for the original Suite writer'
            assert coordinator.commands[0]['status'] == 'completed', coordinator.commands
            assert len(factory.executed) == 1
            assert live.snapshot()['jobs'][0]['cases'][0]['execution_status'] == 'retrying'
    finally:
        coordinator.close()

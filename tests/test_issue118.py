"""Issue #118: explicit ABB result roots, without pretending to write a filename."""
from types import SimpleNamespace

import pytest

from agentbench.cli import execution, viewer
from agentbench.cli.features import evaluate, run, certify
from agentbench.cli.main import build_parser
from agentbench.cli.result_paths import validate_results_dir
from agentbench.cli.sessions import configuration, fresh
from agentbench.harness import SuiteRunner
from agentbench.harness.session import SuiteStore, read_snapshot
from tests.test_suite_concurrency import Factory
from tests.test_suite_resume import make_agent


@pytest.fixture(autouse=True)
def isolate_history(tmp_path, monkeypatch):
    monkeypatch.setattr(fresh, 'PROJECT_ROOT', tmp_path)


@pytest.mark.parametrize('name', ['new-results', 'nested/results.v1', '结果 目录'])
def test_directory_is_created_at_exact_requested_location_and_reopens(tmp_path, monkeypatch, name):
    directory = tmp_path / name
    agent = make_agent(tmp_path, 1)
    monkeypatch.setattr(configuration, 'runner_configuration', lambda _: {'sdk': 'fixture'})
    runner = SuiteRunner(runner_factory=Factory())
    lines = []
    # Start at the real session entry. The fake workers do not need Docker or a service.
    outcome = execution.run_benchmark_session((agent,), runner=runner, output_path=None,
        results_dir=directory, output_fn=lines.append, viewer_starter=None)
    canonical = directory / 'suites' / outcome.result.suite_id / 'events.json'
    assert outcome.result.passed and outcome.result_log.path == canonical.resolve()
    assert canonical.is_file() and (canonical.parent / 'plan.json').is_file()
    assert not (tmp_path / 'suites').exists()
    assert any(f'Result saved: {canonical.resolve()}' in line for line in lines)
    assert any(f'Open later: python -m agentbench view {canonical.resolve()}' in line for line in lines)
    result = viewer.parse_result_log(canonical)
    assert result['suite_id'] == outcome.result.suite_id
    assert result['jobs'][0]['cases'][0]['execution_status'] == 'completed'
    with SuiteStore.open(canonical.parent, environ={}) as store:
        assert store.plan['result_log_path'] == str(canonical.resolve())
        assert 'requested_output_path' not in store.plan
        # Later Judge/recovery events continue writing the same canonical file.
        store.append({'event': 'verification_marker'})
    assert read_snapshot(canonical.parent)['revision'] == result['revision'] + 1


def test_legacy_result_location_is_unchanged(tmp_path):
    agent = make_agent(tmp_path, 1)
    requested = tmp_path / 'named.json'
    writer = fresh.begin_result_log(requested, 'suite_legacy', (agent,), configuration={}, environ={})
    try:
        assert writer.path == tmp_path / 'suites/suite_legacy/events.json'
        assert writer.store.plan['requested_output_path'] == str(requested.resolve())
        assert not requested.exists()
    finally:
        writer.close()


@pytest.mark.parametrize('arguments,legacy', [(['run'], '--output'),
                                           (['evaluate', 'fixture'], '--result-output'),
                                           (['certify', 'fixture'], '--output')])
def test_all_commands_expose_directory_and_reject_conflicting_legacy_option(arguments, legacy, tmp_path):
    parser = build_parser()
    directory = tmp_path / 'results'
    args = parser.parse_args([*arguments, '--results-dir', str(directory)])
    assert args.results_dir == directory
    old = parser.parse_args([*arguments, legacy, str(tmp_path / 'legacy.json')])
    assert old.results_dir is None
    with pytest.raises(SystemExit) as caught:
        parser.parse_args([*arguments, '--results-dir', str(directory), legacy, str(tmp_path / 'legacy.json')])
    assert caught.value.code == 2


def test_invalid_directory_and_python_option_conflict_fail_before_any_dispatch(tmp_path):
    target = tmp_path / 'file.json'
    target.write_text('original', encoding='utf-8')
    with pytest.raises(ValueError, match='directory, not a file'):
        execution.run_benchmark_once((), runner=object(), output_path=None,
            results_dir=target, output_fn=lambda _: None, viewer_starter=None)
    assert target.read_text(encoding='utf-8') == 'original'
    with pytest.raises(ValueError, match='not both'):
        validate_results_dir(tmp_path / 'old.json', tmp_path / 'new')
    assert not (tmp_path / 'new').exists()


def evaluate_fixture(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, 1)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(evaluate, 'execution_environment_snapshot', lambda: SimpleNamespace(environ={}, concurrency=None))
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *args: agent)
    monkeypatch.setattr('agentbench.sdk.strategy_checks.check_agents', lambda *a, **kw: {})
    monkeypatch.setattr('agentbench.cli.terminal_ui.presentation.print_agents', lambda *a, **kw: None)
    return agent


def test_evaluate_routes_abb_directory_separately_from_sdk_output(tmp_path, monkeypatch, capsys):
    agent = evaluate_fixture(tmp_path, monkeypatch)
    built, dispatched = [], []
    monkeypatch.setattr(evaluate, 'build_trace_suite_runner', lambda **kw: built.append(kw) or object())
    monkeypatch.setattr(evaluate, 'run_benchmark_session', lambda *a, **kw: dispatched.append(kw) or SimpleNamespace(result=None, exit_code=0))
    abb, sdk = tmp_path / 'abb-results', tmp_path / 'sdk-output'
    args = build_parser().parse_args(['evaluate', agent.agent_id, '--yes', '--no-view',
                                     '--results-dir', str(abb), '--output', str(sdk)])
    assert evaluate.execute(args) == 0
    assert built[0]['sdk_options']['output'] == sdk
    assert 'results_dir' not in built[0]['sdk_options']
    assert dispatched[0]['results_dir'] == abb.resolve() and dispatched[0]['output_path'] is None
    assert '--results-dir selects the ABB result directory' in capsys.readouterr().out


def test_evaluate_legacy_filename_gets_truthful_migration_notice(tmp_path, monkeypatch, capsys):
    agent = evaluate_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(evaluate, 'build_trace_suite_runner', lambda **kw: object())
    dispatched = []
    monkeypatch.setattr(evaluate, 'run_benchmark_session', lambda *a, **kw: dispatched.append(kw) or SimpleNamespace(result=None, exit_code=0))
    requested = tmp_path / 'named.json'
    args = build_parser().parse_args(['evaluate', agent.agent_id, '--yes', '--no-view', '--result-output', str(requested)])
    assert evaluate.execute(args) == 0
    assert dispatched[0]['output_path'] == requested and 'results_dir' not in dispatched[0]
    output = capsys.readouterr().out
    assert 'Deprecated: --result-output' in output
    assert 'does not create the requested file' in output
    assert '--result-output selects the ABB result JSON' not in output


@pytest.mark.parametrize('module,arguments,call_name', [(run, ['run'], 'run'),
                                                     (certify, ['certify', 'fixture'], 'certify')])
def test_run_and_certify_forward_directory_without_legacy_path(tmp_path, monkeypatch, module, arguments, call_name):
    monkeypatch.setattr(module, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(module, 'execution_environment_snapshot', lambda: SimpleNamespace(environ={}, concurrency=None))
    forwarded = []
    if module is run:
        monkeypatch.setattr(module, call_name, lambda config: forwarded.append(config) or 0)
    else:
        monkeypatch.setattr(module, call_name, lambda *a, **kw: forwarded.append(SimpleNamespace(**kw)) or 0)
    directory = tmp_path / 'out'
    args = build_parser().parse_args([*arguments, '--results-dir', str(directory), '--yes', '--no-view'])
    assert module.execute(args) == 0
    assert forwarded[0].results_dir == directory.resolve()
    assert forwarded[0].output_path is None


def test_directory_selection_survives_viewer_rerun(tmp_path, monkeypatch):
    forwarded, stopped = [], []
    selected = tmp_path / 'new-results'
    def once(*args, **kwargs):
        forwarded.append(kwargs)
        return SimpleNamespace(result_log=SimpleNamespace(path=selected / 'suites' / f'suite_{len(forwarded)}' / 'events.json'),
                               viewer=SimpleNamespace(url='http://localhost/verification'))
    actions = iter(['rerun', 'quit'])
    monkeypatch.setattr(execution, 'run_benchmark_once', once)
    monkeypatch.setattr(execution, 'stop_viewer', lambda value: stopped.append(value))
    monkeypatch.setattr('agentbench.cli.terminal_ui.presentation.request_viewer_action', lambda *a, **kw: next(actions))
    outcome = execution.run_benchmark_session((), runner=object(), output_path=None,
        results_dir=selected, output_fn=lambda _: None, viewer_starter=object())
    assert len(forwarded) == len(stopped) == 2
    assert all(value['results_dir'] == selected and value['output_path'] is None for value in forwarded)
    assert outcome.result_log.path.parent.name == 'suite_2'

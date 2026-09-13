"""All benchmark commands share viewer policy and the session lifecycle."""
import json
from types import SimpleNamespace
import pytest
from agentbench.cli import execution
from agentbench.cli.main import build_parser


@pytest.mark.parametrize('command', ['run', 'certify', 'evaluate'])
def test_viewer_policy_defaults_on_and_can_be_disabled(command):
    arguments = [command] + (['agent'] if command == 'certify' else [])
    parser = build_parser()
    assert not parser.parse_args(arguments).no_view
    assert parser.parse_args(arguments + ['--no-view']).no_view


def test_shared_session_closes_each_viewer_and_reruns(monkeypatch, tmp_path):
    stopped, runs = [], []
    def once(*args, **kwargs):
        index = len(runs)
        result = execution.BenchmarkExecution(0, None,
            SimpleNamespace(path=tmp_path / f'{index}.json'),
            SimpleNamespace(url='http://localhost/test', stop=lambda: stopped.append(index)))
        runs.append(result)
        return result
    monkeypatch.setattr(execution, 'run_benchmark_once', once)
    answers = iter(['r', 'q'])
    result = execution.run_benchmark_session((), runner=object(), output_path=tmp_path,
        output_fn=lambda _: None, viewer_starter=object(), input_fn=lambda _: next(answers))
    assert len(runs) == 2 and stopped == [0, 1] and result is runs[-1]


def test_session_without_viewer_never_prompts(monkeypatch):
    expected = execution.BenchmarkExecution(1, None, None, None)
    monkeypatch.setattr(execution, 'run_benchmark_once', lambda *a, **kw: expected)
    result = execution.run_benchmark_session((), runner=object(), output_path=None,
        output_fn=lambda _: None, viewer_starter=None,
        input_fn=lambda _: pytest.fail('headless execution must not prompt'))
    assert result is expected


def test_session_closes_viewer_when_prompt_fails(monkeypatch):
    stopped = []
    value = execution.BenchmarkExecution(0, None, SimpleNamespace(path='result.json'),
        SimpleNamespace(url='http://localhost/test', stop=lambda: stopped.append(True)))
    monkeypatch.setattr(execution, 'run_benchmark_once', lambda *a, **kw: value)
    def fail(_):
        raise RuntimeError('input failed')
    with pytest.raises(RuntimeError, match='input failed'):
        execution.run_benchmark_session((), runner=object(), output_path=None,
            output_fn=lambda _: None, viewer_starter=object(), input_fn=fail)
    assert stopped == [True]


@pytest.mark.parametrize('command', ['run', 'certify', 'evaluate'])
def test_sdk_source_is_selectable_on_every_command_that_drives_an_sdk(command, tmp_path):
    from agentbench.cli.sdk import sdk_arguments
    arguments = [command] + (['agent'] if command == 'certify' else [])
    parser = build_parser()
    assert 'sdk_options' not in sdk_arguments(parser.parse_args(arguments))
    args = parser.parse_args(arguments + ['--sdk-source', str(tmp_path)])
    assert sdk_arguments(args)['sdk_options'] == {'sdk_source': tmp_path}


def test_missing_kuma_source_reports_the_path_it_tried(tmp_path):
    from agentbench.harness.errors import ProviderSelectionError
    from agentbench.sdk.kuma.benchmark import KumaContainerRunner
    agent = tmp_path / 'agent'; (agent / 'evaluation').mkdir(parents=True)
    (agent / 'evaluation/profile.md').write_text('---\n---\n')
    (agent / 'evaluation/input-contract.json').write_text('{}')
    absent = tmp_path / 'nowhere'
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'fixture'}, options={'sdk_source': absent})
    with pytest.raises(ProviderSelectionError) as raised:
        runner.validate_sdk(SimpleNamespace(path=agent))
    assert str(absent) in str(raised.value)


@pytest.mark.parametrize('command', ['run', 'certify', 'evaluate'])
def test_every_spending_command_offers_the_same_confirmation_opt_out(command):
    arguments = [command] + (['agent'] if command == 'certify' else [])
    parser = build_parser()
    assert parser.parse_args(arguments).yes is False
    assert parser.parse_args(arguments + ['--yes']).yes is True


def test_evaluate_stops_at_its_own_charge_warning_without_consent(
        starter_agent, repo_root, monkeypatch, capsys):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    started = []
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: starter_agent)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(evaluate, 'run_benchmark_session',
                        lambda *a, **kw: started.append(a))
    monkeypatch.chdir(repo_root)
    assert cli(['evaluate', '1', '--sdk', 'python:examples.case_file_sdk',
                '--sdk-options', 'examples/case_file_options.json']) == 0
    assert started == []
    output = capsys.readouterr().out
    assert 'may incur charges' in output and 'cancelled' in output


# `observe --list` answers from the registry alone and never loads an env file.
@pytest.mark.parametrize('command,label,fault', [
    (command, label, fault)
    for command, label in [('run', 'Run failed'), ('certify', 'Certification failed'),
                           ('observe', 'Observe failed'), ('evaluate', 'Evaluation failed')]
    for fault in ['registry', 'env_file']
    if not (command == 'observe' and fault == 'env_file')
])
def test_a_missing_input_file_is_a_diagnostic_line_on_every_command(
        command, label, fault, tmp_path, capsys, monkeypatch):
    from agentbench.cli.main import cli
    from agentbench.cli.terminal_ui import constants
    monkeypatch.setattr(constants, 'LOGO_PAUSE_SECONDS', 0)
    monkeypatch.setattr('agentbench.cli.features.run.LOGO_PAUSE_SECONDS', 0)
    absent = tmp_path / 'absent'
    arguments = [command]
    if command in ('certify', 'evaluate'):
        arguments.append('react-agent')
    if command == 'observe':
        arguments.append('--list')
    if fault == 'registry':
        arguments += ['--registry', str(absent / 'registry.toml')]
    else:
        arguments += ['--env-file', str(absent / '.env')]
    if command in ('run', 'certify', 'evaluate'):
        arguments.append('--no-view')

    assert cli(arguments) == 1
    output = capsys.readouterr().out
    assert label in output and str(absent) in output
    assert 'Traceback' not in output


@pytest.mark.parametrize('verdict,expected_exit', [('pass', 0), ('issue', 1)])
def test_evaluate_exit_code_follows_the_judge_verdict(
        starter_agent, repo_root, monkeypatch, tmp_path, capsys, verdict, expected_exit):
    from agentbench.cli.main import cli
    from agentbench.cli.features import evaluate
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': starter_agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *_: starter_agent)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.chdir(repo_root)
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inputs': [{
        'input_id': 'only', 'payload': 'Hello ABB',
        'expected_output': 'Hello ABB' if verdict == 'pass' else 'something else'}]}))
    options = tmp_path / 'options.json'
    options.write_text(json.dumps({'case_file': str(case)}))
    exit_code = cli(['evaluate', '1', '--yes', '--no-view', '--sdk', 'python:examples.case_file_sdk',
                     '--sdk-options', str(options), '--result-output', str(tmp_path / 'result.json')])
    output = capsys.readouterr().out
    # The verdict is reported either way; only the exit code distinguishes them.
    assert f'Judge: {verdict}' in output
    assert exit_code == expected_exit

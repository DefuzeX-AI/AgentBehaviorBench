"""All benchmark commands share viewer policy and the session lifecycle."""
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

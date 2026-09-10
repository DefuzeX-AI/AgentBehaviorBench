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

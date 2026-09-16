"""Issue #32: a completed execution survives loss of the post-run console."""
from types import SimpleNamespace

import pytest

from agentbench.cli import execution


@pytest.mark.parametrize('error', [EOFError, OSError, RuntimeError, KeyboardInterrupt])
def test_closed_stdin_preserves_execution_and_stops_viewer(monkeypatch, tmp_path, error):
    stopped = []
    viewer = SimpleNamespace(url='http://localhost', stop=lambda: stopped.append(True))
    completed = execution.BenchmarkExecution(0, object(), SimpleNamespace(path=tmp_path/'run.json'), viewer)
    monkeypatch.setattr(execution, 'run_benchmark_once', lambda *a, **kw: completed)

    def closed(prompt): raise error('console unavailable')

    actual = execution.run_benchmark_session((), runner=object(), output_path=None,
        output_fn=lambda text: None, viewer_starter=None, input_fn=closed)
    assert actual is completed
    assert stopped == [True]

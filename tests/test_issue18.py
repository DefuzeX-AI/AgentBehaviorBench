"""Issue #18: both single-Agent commands honour declined confirmation."""
from agentbench.cli.features import evaluate, certify
from agentbench.cli.main import build_parser


def test_evaluate_decline_never_constructs_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(evaluate, 'input', lambda prompt: 'no', raising=False)
    monkeypatch.setattr(evaluate, 'build_trace_suite_runner', lambda **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    args = build_parser().parse_args(['evaluate', 'react-agent', '--no-view', '--result-output', str(tmp_path/'r.json')])
    assert evaluate.execute(args) == 0
    assert not (tmp_path/'r.json').exists()


def test_certify_decline_never_constructs_runner(monkeypatch):
    monkeypatch.setattr(certify, 'build_trace_suite_runner', lambda **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    assert certify.certify('react-agent', input_fn=lambda _: 'no', output_fn=lambda _: None) == 0

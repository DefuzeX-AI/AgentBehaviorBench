"""Issue #18: both single-Agent commands honour declined confirmation."""
from agentbench.cli.features import evaluate, certify
from agentbench.cli.main import build_parser
from types import SimpleNamespace
import pytest


@pytest.fixture
def adapting_agent(tmp_path, monkeypatch):
    """Confirmation tests must not depend on the user's enabled registry entries."""
    from dataclasses import replace
    from tests.test_suite_resume import make_agent
    agent = replace(make_agent(tmp_path, 1), status='adapting')
    monkeypatch.setattr('agentbench.sdk.strategy_checks.check_agents', lambda *a, **kw: {})
    monkeypatch.setattr(evaluate, 'execution_environment_snapshot', lambda: SimpleNamespace(environ={}, concurrency=None))
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': agent.agent_id}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *a: agent)
    monkeypatch.setattr(certify, 'load_registry', lambda _: SimpleNamespace(find=lambda _: agent))
    return agent


def test_evaluate_decline_never_constructs_runner(monkeypatch, tmp_path, adapting_agent):
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(evaluate, 'input', lambda prompt: 'no', raising=False)
    monkeypatch.setattr(evaluate, 'build_trace_suite_runner', lambda **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    args = build_parser().parse_args(['evaluate', adapting_agent.agent_id, '--no-view', '--result-output', str(tmp_path/'r.json')])
    assert evaluate.execute(args) == 0
    assert not (tmp_path/'r.json').exists()


def test_certify_decline_never_constructs_runner(monkeypatch, adapting_agent):
    monkeypatch.setattr(certify, 'build_trace_suite_runner', lambda **kw: (_ for _ in ()).throw(AssertionError('must not run')))
    assert certify.certify(adapting_agent.agent_id, input_fn=lambda _: 'no', output_fn=lambda _: None) == 0

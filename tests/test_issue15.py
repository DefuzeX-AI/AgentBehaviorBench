"""Issue #15: evaluate exposes all Judge verdicts and their aggregate exit code."""
from types import SimpleNamespace as NS

import pytest

from agentbench.cli.features import evaluate
from agentbench.cli.main import build_parser


@pytest.mark.parametrize('statuses,expected', [(['pass'], 0), (['issue'], 1),
    (['insufficient_evidence'], 1), (['issue', 'pass'], 1)])
def test_evaluate_exit_follows_every_judge(monkeypatch, tmp_path, statuses, expected):
    agent = NS(agent_id='agent', case_count=len(statuses))
    reports = [NS(report=NS(status=s)) for s in statuses]
    item = NS(error_type=None, completed_case_count=len(statuses),
              requested_case_count=len(statuses), benchmarks=reports)
    result = NS(items=[item], passed=expected == 0)
    monkeypatch.setattr(evaluate, 'load_project_environment', lambda _: None)
    monkeypatch.setattr(evaluate, 'execution_environment_snapshot', lambda: NS(environ={}, concurrency=None))
    monkeypatch.setattr(evaluate, 'enabled_agents', lambda _: [{'agent_id': 'agent'}])
    monkeypatch.setattr(evaluate, 'resolve_agent', lambda *a: agent)
    monkeypatch.setattr(evaluate, 'build_trace_suite_runner', lambda **kw: object())
    monkeypatch.setattr(evaluate, 'run_benchmark_session',
                        lambda *a, **kw: NS(result=result, exit_code=expected))
    args = build_parser().parse_args(['evaluate', 'agent', '--no-view', '--result-output', str(tmp_path/'run.json')])
    args.yes = True
    assert evaluate.execute(args) == expected

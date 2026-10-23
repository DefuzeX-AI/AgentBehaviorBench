from types import SimpleNamespace
import importlib
import pytest

from agentbench.cli.configuration import RunConfiguration
from agentbench.harness.registry import AgentRegistry


@pytest.mark.parametrize('selection,expected', [(('a',), ('a',)), (('b', 'a'), ('a', 'b'))])
def test_run_filters_before_confirmation(monkeypatch, selection, expected):
    feature = importlib.import_module('agentbench.cli.features.run')
    registry = AgentRegistry([SimpleNamespace(agent_id=x, enabled=True, status='ready') for x in ('a', 'b')])
    monkeypatch.setattr(feature, 'load_registry', lambda _: registry)
    monkeypatch.setattr(feature, 'print_logo', lambda _: None)
    monkeypatch.setattr(feature.time, 'sleep', lambda _: None)
    seen = []
    monkeypatch.setattr(feature, 'confirm_agents', lambda agents, **kw: seen.append(tuple(a.agent_id for a in agents)) or False)
    assert feature.run(RunConfiguration(agent_ids=selection, suite_runner=object(), output_fn=lambda _: None)) == 0
    assert seen == [expected]


def test_run_rejects_unknown_selection(monkeypatch):
    feature = importlib.import_module('agentbench.cli.features.run')
    monkeypatch.setattr(feature, 'load_registry', lambda _: AgentRegistry([]))
    monkeypatch.setattr(feature, 'print_logo', lambda _: None)
    monkeypatch.setattr(feature.time, 'sleep', lambda _: None)
    with pytest.raises(ValueError, match='not enabled and ready'):
        feature.run(RunConfiguration(agent_ids=('unknown',), output_fn=lambda _: None))

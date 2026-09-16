"""The outer Company binding preserves the upstream report success condition."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import pytest


@pytest.fixture
def binding(monkeypatch):
    observed = []
    class Graph:
        def __init__(self, **inputs):
            observed.append(inputs)
        async def run(self, thread):
            observed.append(thread)
            yield {"grounding": {"company": "Acme"}}
            yield {"editor": Graph.result}
    Graph.result = {"report": "Native research report"}
    backend = ModuleType("backend")
    backend.__path__ = []
    graph = ModuleType("backend.graph")
    graph.Graph = Graph
    monkeypatch.setitem(sys.modules, "backend", backend)
    monkeypatch.setitem(sys.modules, "backend.graph", graph)
    path = Path(__file__).resolve().parents[1] / "resources/agents/01-company-research-agent/bindings/bridge.py"
    spec = importlib.util.spec_from_file_location("company_binding_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_graph(), Graph, observed


def test_actual_input_config_and_native_report_are_preserved(binding):
    instance, graph, observed = binding
    config = {"metadata": {"test": "forward"}}
    result = asyncio.run(instance.ainvoke({"company": "Acme", "company_url": "https://example.com"}, config))
    assert observed[0]["company"] == "Acme" and observed[0]["url"] == "https://example.com"
    assert observed[1] is config
    assert result["editor"]["report"] == "Native research report"


@pytest.mark.parametrize("result", [{}, {"report": ""}, {"report": "  "}, {"report": None}])
def test_missing_report_is_failure_even_if_native_nodes_do_not_raise(binding, result):
    instance, graph, observed = binding
    graph.result = result
    with pytest.raises(RuntimeError, match="without a non-empty report"):
        asyncio.run(instance.ainvoke({"company": "Acme"}))

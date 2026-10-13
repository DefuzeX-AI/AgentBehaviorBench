"""The outer Company binding preserves the upstream report success condition."""
import asyncio
import sys
from collections import defaultdict
from types import ModuleType, SimpleNamespace
import pytest
from tests.registered_agents import binding as registered_binding


@pytest.fixture
def binding(monkeypatch):
    observed = []
    class Graph:
        def __init__(self, **inputs):
            observed.append(inputs)
            self.briefing = SimpleNamespace(llm=SimpleNamespace(
                client=SimpleNamespace(transport=SimpleNamespace(close=lambda: None))))
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
    classes = ModuleType("backend.classes")
    state = ModuleType("backend.classes.state")
    state.job_status = defaultdict(dict)
    monkeypatch.setitem(sys.modules, "backend.classes", classes)
    monkeypatch.setitem(sys.modules, "backend.classes.state", state)
    instance = registered_binding('company-research-agent').create_graph()
    try:
        yield instance, Graph, observed
    finally:
        instance.close()
        assert not state.job_status



def test_actual_input_config_and_native_report_are_preserved(binding):
    instance, graph, observed = binding
    config = {"metadata": {"test": "forward"}}
    result = asyncio.run(instance.ainvoke({"company": "Acme", "company_url": "https://example.com"}, config))
    assert observed[0]["company"] == "Acme" and observed[0]["url"] == "https://example.com"
    assert observed[1]["metadata"]["test"] == config["metadata"]["test"]
    assert result["report"] == "Native research report"


@pytest.mark.parametrize("result", [{}, {"report": ""}, {"report": "  "}, {"report": None}])
def test_missing_report_is_failure_even_if_native_nodes_do_not_raise(binding, result):
    instance, graph, observed = binding
    graph.result = result
    with pytest.raises(RuntimeError, match="without a non-empty report"):
        asyncio.run(instance.ainvoke({"company": "Acme"}))

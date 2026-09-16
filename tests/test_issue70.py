"""Issue #70: observing an Agent must not require a newer LangGraph than the Agent pins."""
import importlib
import sys
from types import ModuleType
from uuid import uuid4

import pytest

import agentbench.observe.langchain as observe_langchain


class Store:
    def __init__(self):
        self.events = []

    def record(self, event, **data):
        self.events.append((event, data))


@pytest.fixture
def langgraph_errors(monkeypatch):
    """Reload the callback module against a stand-in langgraph.errors, then restore it."""
    def install(**classes):
        module = ModuleType("langgraph.errors")
        for name, value in classes.items():
            setattr(module, name, value)
        monkeypatch.setitem(sys.modules, "langgraph.errors", module)
        return importlib.reload(observe_langchain)
    yield install
    monkeypatch.undo()
    importlib.reload(observe_langchain)


def _error_event(module, error):
    store = Store()
    callback = module.TraceCallback(store)
    callback.on_chain_error(error, run_id=uuid4())
    return store.events[-1][0]


def test_langgraph_before_graph_bubble_up_treats_interrupts_as_control_flow(langgraph_errors):
    class GraphInterrupt(Exception):
        pass
    module = langgraph_errors(GraphInterrupt=GraphInterrupt)  # langgraph 0.1 to 0.2.40
    assert module.GRAPH_CONTROL_FLOW is GraphInterrupt
    assert _error_event(module, GraphInterrupt("pause")) == "span_control"
    assert _error_event(module, ValueError("real failure")) == "span_error"


def test_langgraph_without_control_flow_exceptions_still_observes(langgraph_errors):
    module = langgraph_errors()  # langgraph 0.0.x: the module exists, the classes do not
    assert module.GRAPH_CONTROL_FLOW == ()
    assert _error_event(module, ValueError("real failure")) == "span_error"


def test_current_langgraph_keeps_graph_bubble_up():
    from langgraph.errors import GraphBubbleUp, GraphInterrupt
    assert observe_langchain.GRAPH_CONTROL_FLOW is GraphBubbleUp
    assert _error_event(observe_langchain, GraphInterrupt("pause")) == "span_control"

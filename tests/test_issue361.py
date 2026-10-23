"""Target-only credential-free regressions for Issue #361 onboarding.

These are unit contracts, not a target Agent execution or a Judge evaluation.
"""
from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tests.test_issue214_zhisaotong import _binding


def test_offline_diagnostic_has_no_chat_or_graph_invocation():
    """Guard the diagnostic's no-model boundary, not a fabricated Agent result."""
    path = (Path(__file__).resolve().parents[1] / "resources" / "agents"
            / "44-zhisaotong-agent" / "bindings" / "offline_check.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    forbidden = {"ainvoke", "stream", "astream", "rag_summarize"}
    assert not any(isinstance(node.func, ast.Attribute) and node.func.attr in forbidden
                   for node in calls)
    invocations = [node.func.value for node in calls
                   if isinstance(node.func, ast.Attribute) and node.func.attr == "invoke"]
    assert len(invocations) == 1
    assert ast.unparse(invocations[0]) == "agent_tools.fetch_external_data"


def test_empty_native_knowledge_index_is_an_initialization_failure(tmp_path, monkeypatch):
    """The native loader catches document errors; the binding must detect emptiness."""
    import sys

    module = _binding()
    utils = ModuleType("utils")
    utils.config_handler = SimpleNamespace(chroma_conf={})
    vector_store = ModuleType("rag.vector_store")
    calls = []

    class EmptyStore:
        def get(self, *, limit):
            calls.append(("get", limit))
            return {"ids": []}

    class Service:
        vector_store = EmptyStore()

        def load_document(self):
            calls.append(("load_document",))

    vector_store.VectorStoreService = Service
    monkeypatch.setitem(sys.modules, "utils", utils)
    monkeypatch.setitem(sys.modules, "rag.vector_store", vector_store)
    with pytest.raises(RuntimeError, match="Knowledge index is empty"):
        module._build_knowledge_index(tmp_path)
    assert calls == [("load_document",), ("get", 1)]


@pytest.mark.parametrize("asynchronous", [False, True])
def test_native_config_is_forwarded_without_replacing_errors(monkeypatch, asynchronous):
    """A failing native graph must not become a fabricated successful response."""
    graph = _binding().create_graph()
    config = {"tags": ["issue361"], "metadata": {"case": "unit-contract"}}
    failure = RuntimeError("native execution failed")
    calls = []

    class NativeGraph:
        def invoke(self, payload, config=None, *, context=None):
            calls.append((payload, config, context))
            raise failure

    monkeypatch.setattr(graph, "_load", lambda: SimpleNamespace(agent=NativeGraph()))
    try:
        with pytest.raises(RuntimeError) as caught:
            if asynchronous:
                asyncio.run(graph.ainvoke("question", config=config))
            else:
                graph.invoke("question", config=config)
        assert caught.value is failure
        assert calls == [(
            {"messages": [{"role": "user", "content": "question"}]},
            config,
            {"report": False},
        )]
        assert calls[0][1] is config
    finally:
        graph.close()

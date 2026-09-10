import json
from agentbench.observe.store import TraceStore, atomic_json
from agentbench.observe.review import render_review


def test_incomplete_trace_never_validates_as_success():
    from agentbench.runtime.interception.trace import InterceptionTraceState, TraceEvent
    for failure in ("truncated", "llm_error", "write_failure"):
        state = InterceptionTraceState()
        state.emit(TraceEvent("llm_request", {"call_id": "a"}))
        state.emit(TraceEvent("llm_response", {"call_id": "a", "truncated": failure == "truncated"}))
        if failure == "llm_error":
            state.emit(TraceEvent("llm_error", {"call_id": "a"}))
        if failure == "write_failure":
            state.fail()
        assert not state.wait_for_completion_after(0, 0.01)
        assert not state.wait_for_idle(timeout=0.01, quiet=0)


def test_redaction_and_incomplete_review(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "sensitive-value")
    atomic_json(tmp_path / "run.json", {"run_id": "run", "agent_id": "a", "status": "failed"})
    store = TraceStore(tmp_path / "framework.jsonl", "run", source="framework")
    store.record("span_start", span_id="parent", parent_span_id=None, name="LangGraph")
    store.record("span_start", span_id="child", parent_span_id="parent", name="node", input="sensitive-value", api_key="hidden")
    store.record("span_error", span_id="child", error="sensitive-value")
    text = (tmp_path / "framework.jsonl").read_text()
    assert "sensitive-value" not in text and "hidden" not in text
    rendered = render_review(tmp_path)
    assert "LangGraph [incomplete]" in rendered
    assert "node [error]" in rendered


def test_unicode_line_separators_are_not_jsonl_record_boundaries(tmp_path):
    from agentbench.observe.store import summarize
    from agentbench.observe.review import read_events
    store = TraceStore(tmp_path / "framework.jsonl", "run", source="framework")
    value = "中文\u0085\u2028\u2029完整"
    store.record("span_end", span_id="one", output=value)
    assert list(read_events(tmp_path))[0]["data"]["output"] == value
    assert summarize(tmp_path) == {"framework:span_end": 1}


def test_partial_tool_failure_preserves_result_and_marks_trace(tmp_path):
    import asyncio
    import importlib.util
    from pathlib import Path
    from agentbench.observe.tools import observe_async_methods
    from agentbench.observe.langchain import TraceCallback
    from agentbench.observe.store import summarize
    spec = importlib.util.spec_from_file_location("company_outcomes",
        Path(__file__).resolve().parents[2] / "resources/agents/01-company-research-agent/bindings/company.py")
    company = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(company)
    original = {"results": [{"url": "good"}], "failed_results": [{"url": "bad", "error": "timeout"}]}
    class Tool:
        async def extract(self, value):
            return original
    client = Tool()
    observe_async_methods(client, ("extract",), namespace="tavily", inspect_result=company.tavily_outcome)
    store = TraceStore(tmp_path / "framework.jsonl", "run", source="framework")
    from langchain_core.runnables import RunnableLambda
    async def run(value):
        return await client.extract(value)
    result = asyncio.run(RunnableLambda(run).ainvoke("x", config={"callbacks": [TraceCallback(store)]}))
    assert result is original
    assert summarize(tmp_path)["framework:tool_incomplete"] == 1

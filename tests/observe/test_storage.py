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

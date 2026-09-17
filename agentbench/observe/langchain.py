"""LangChain callbacks: real execution IDs and parent IDs, no fabricated spans."""
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import ToolMessage
from .correlation import current_span

# LangGraph control flow that bubbles through callbacks is not an error. This runs
# inside the Agent's own environment, so accept the LangGraph the Agent pins: current
# releases raise GraphBubbleUp; older ones (0.1 to 0.2.40 measured) only GraphInterrupt.
try:
    from langgraph.errors import GraphBubbleUp as GRAPH_CONTROL_FLOW
except ImportError:
    try:
        from langgraph.errors import GraphInterrupt as GRAPH_CONTROL_FLOW
    except ImportError:
        GRAPH_CONTROL_FLOW = ()


class TraceCallback(BaseCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, store):
        self.store = store

    def _start(self, kind, serialized, value, run_id, parent_run_id, **kwargs):
        current_span.set(str(run_id))
        if (kwargs.get("metadata") or {}).get("abb_span_kind") == "tool":
            kind = "tool"
        self.store.record("span_start", kind=kind, span_id=str(run_id),
                          parent_span_id=str(parent_run_id) if parent_run_id else None,
                          name=kwargs.get("name") or (serialized or {}).get("name", kind),
                          input=value, metadata=kwargs.get("metadata"), tool_call_id=kwargs.get('tool_call_id'))

    def _end(self, value, run_id, **kwargs):
        current_span.set(str(kwargs["parent_run_id"]) if kwargs.get("parent_run_id") else None)
        self.store.record("span_end", span_id=str(run_id), output=value,
                          tool_call_id=kwargs.get('tool_call_id'), tool_status=kwargs.get('tool_status'))

    def _error(self, error, run_id, **kwargs):
        current_span.set(str(kwargs["parent_run_id"]) if kwargs.get("parent_run_id") else None)
        if isinstance(error, GRAPH_CONTROL_FLOW):
            self.store.record("span_control", span_id=str(run_id), control=type(error).__name__)
            return
        self.store.record("span_error", span_id=str(run_id), error=str(error))

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self._start("chain", serialized, inputs, run_id, parent_run_id, **kwargs)

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._start("llm", serialized, messages, run_id, parent_run_id, **kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        self._start("llm", serialized, prompts, run_id, parent_run_id, **kwargs)

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        value = kwargs['inputs'] if kwargs.get('inputs') is not None else input_str
        self._start("tool", serialized, value, run_id, parent_run_id, **kwargs)

    def on_tool_end(self, output, *, run_id, **kwargs):
        if isinstance(output, ToolMessage):
            kwargs.update(tool_call_id=output.tool_call_id, tool_status=output.status)
            output = output.content
        self._end(output, run_id, **kwargs)

    on_chain_end = _end
    on_llm_end = _end
    on_chain_error = _error
    on_llm_error = _error
    on_tool_error = _error

    def on_custom_event(self, name, data, *, run_id, **kwargs):
        if name == "abb.tool_outcome":
            self.store.record("tool_outcome", span_id=str(run_id), **data)
            return
        self.store.record("native_event", name=name, span_id=str(run_id), payload=data)

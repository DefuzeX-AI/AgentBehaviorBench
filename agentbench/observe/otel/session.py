"""Convert live framework notifications to real OTel spans, never replay logs."""
import threading
import json
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode
from agentbench.observe.store import atomic_json, redact
from .exporter import FileExporter
from .routing import attach


class OtelSession:
    def __init__(self, directory, invocation_id, session_id, secrets=(), provider=None):
        existing = provider or trace.get_tracer_provider()
        self.owned = not isinstance(existing, TracerProvider)
        self.provider = TracerProvider(resource=Resource.create({'service.name': 'abb-agent'})) if self.owned else existing
        self.exporter = FileExporter(directory, invocation_id, session_id, secrets)
        self.router = attach(self.provider, self.exporter)
        self.tracer = self.provider.get_tracer('agentbench.observe')
        self.invocation_id, self.directory = invocation_id, directory
        self.spans = {}
        self.root = None
        self.lock = threading.RLock()
        self.error = None

    def _tool_content(self, span, label, value):
        """Attach observed JSON tool content; unsupported values stay omitted."""
        try:
            payload = json.dumps(redact(value, self.exporter.secrets), ensure_ascii=True, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            span.set_attribute(f'abb.tool_{label}_omission', 'not_json_serializable')
            return
        span.set_attribute(f'gen_ai.tool.call.{label}', payload)

    def record(self, event, **data):
        with self.lock:
            identity = {f'abb.{key}': data[key] for key in ('input_id', 'case_id', 'agent_id') if isinstance(data.get(key), str)}
            if event == 'execution_start':
                self.root = self.tracer.start_span('abb.execute', context=Context(), attributes={
                    'abb.invocation_id': self.invocation_id, 'gen_ai.operation.name': 'invoke_agent', **identity})
                self.exporter.payload(self.root, 'input', data.get('input'))
            elif event == 'span_start':
                parent_id = data.get('parent_span_id')
                parent = self.spans.get(parent_id) if parent_id else self.root
                if parent is None:
                    self.error = 'Missing parent span'
                kind = data.get('kind', 'chain')
                operation = {'llm': 'chat', 'tool': 'execute_tool'}.get(kind, 'invoke_agent')
                span = self.tracer.start_span(data.get('name', kind),
                    context=trace.set_span_in_context(parent, Context()) if parent else Context(),
                    attributes={'abb.invocation_id': self.invocation_id, 'abb.framework_span_id': data['span_id'],
                                'abb.kind': kind, 'gen_ai.operation.name': operation, **identity})
                if data['span_id'] in self.spans:
                    raise ValueError('Duplicate framework span start')
                self.spans[data['span_id']] = span
                if kind == 'tool':
                    span.set_attribute('gen_ai.tool.name', data.get('name', 'tool'))
                    span.set_attribute('gen_ai.tool.type', 'function')
                    if isinstance(data.get('tool_call_id'), str):
                        span.set_attribute('gen_ai.tool.call.id', data['tool_call_id'])
                    if 'input' in data:
                        self._tool_content(span, 'arguments', data['input'])
                self.exporter.payload(span, 'input', data.get('input'))
                self.exporter.payload(span, 'metadata', data.get('metadata'))
            elif event == 'span_update':
                span = self.spans.get(data['span_id'])
                if span is not None and 'input' in data:
                    self._tool_content(span, 'arguments', data['input'])
                    self.exporter.payload(span, 'input', data['input'])
            elif event in ('span_end', 'span_error', 'span_control'):
                span = self.spans.pop(data['span_id'], None)
                if span is None:
                    self.error = 'Missing span start'
                    return
                label = 'error' if event == 'span_error' else 'output'
                self.exporter.payload(span, label, data.get(label))
                if event == 'span_end' and span.attributes.get('abb.kind') == 'tool':
                    if 'output' in data:
                        self._tool_content(span, 'result', data['output'])
                    else:
                        span.set_attribute('abb.tool_result_omission', 'not_observed')
                    if 'gen_ai.tool.call.arguments' not in span.attributes:
                        span.set_attribute('abb.tool_arguments_omission', 'not_observed')
                    if isinstance(data.get('tool_call_id'), str):
                        span.set_attribute('gen_ai.tool.call.id', data['tool_call_id'])
                    if data.get('tool_status') == 'error':
                        span.set_status(Status(StatusCode.ERROR, 'Tool returned an error outcome'))
                if event == 'span_error':
                    span.set_status(Status(StatusCode.ERROR, 'Agent step raised an exception'))
                elif event == 'span_control':
                    span.set_attribute('abb.control_flow', data['control'])
                span.end()
            elif event in ('execution_end', 'execution_error') and self.root:
                label = 'output' if event == 'execution_end' else 'error'
                self.exporter.payload(self.root, label, data.get(label))
                if event == 'execution_error':
                    self.root.set_status(Status(StatusCode.ERROR, 'Agent execution failed'))
            elif event in ('native_event', 'tool_outcome'):
                span = self.spans.get(data.get('span_id')) or self.root
                if span:
                    self.exporter.event(span, data.get('name', event), data,
                                        span_event=data.get('span_event', True))

    def close(self):
        with self.lock:
            unfinished = len(self.spans)
            for span in self.spans.values():
                span.set_attribute('abb.incomplete', True)
                span.set_status(Status(StatusCode.ERROR, 'Step did not finish before execution closed'))
                span.end()
            self.spans.clear()
            if self.root:
                self.root.end()
                self.root = None
            try:
                flushed = self.provider.force_flush()
                error = self.exporter.error or self.error
                atomic_json(self.directory / 'otel-status.json', {
                    'status': 'complete' if not error and not unfinished and flushed else 'incomplete',
                    'unfinished_spans': unfinished, 'error': error})
            finally:
                self.router.detach(self.exporter)
                self.exporter.shutdown()
                if self.owned:
                    self.provider.shutdown()



class ObservedStore:
    """Keep trace failures separate from Agent execution and original JSONL."""
    def __init__(self, store, invocation_id, *, provider=None):
        self.store = store
        self.path, self.run_id = store.path, store.run_id
        self.otel = OtelSession(store.path.parent, invocation_id, store.run_id, store._secrets, provider=provider)

    def record(self, event, **data):
        data = {**data, **self.store.context}
        self.store.record(event, **data)
        try:
            self.otel.record(event, **data)
        except Exception as exc:
            self.otel.error = type(exc).__name__

    def close(self):
        self.otel.close()

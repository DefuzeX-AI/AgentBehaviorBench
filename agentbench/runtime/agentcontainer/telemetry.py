"""Serialize original ended OTel spans across an isolated process boundary."""
import json
from agentbench.observe.store import redact, environment_secrets
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class WireExporter(SpanExporter):
    def __init__(self):
        self.destination = None
        self.error = None
        self.secrets = environment_secrets()

    def add_secrets(self, secrets):
        values = tuple(value for value in secrets if isinstance(value, str) and value)
        if values:
            self.secrets = tuple(dict.fromkeys((*self.secrets, *values)))

    def export(self, spans):
        try:
            if self.destination is None:
                raise RuntimeError('No active invocation for telemetry')
            with self.destination.open('a', encoding='utf-8') as stream:
                for span in spans:
                    row = json.loads(span.to_json())
                    row['start_time_ns'] = span.start_time
                    row['end_time_ns'] = span.end_time
                    row['trace_flags'] = int(span.context.trace_flags)
                    scope = span.instrumentation_scope
                    row['event_times_ns'] = [e.timestamp for e in span.events]
                    row['scope'] = {'name': scope.name, 'version': scope.version} if scope else None
                    row['dropped_attributes'] = span.dropped_attributes
                    row['dropped_events'] = span.dropped_events
                    row['dropped_links'] = span.dropped_links
                    stream.write(json.dumps(redact(row, self.secrets), ensure_ascii=False) + '\n')
                stream.flush()
            return SpanExportResult.SUCCESS
        except Exception as exc:
            self.error = type(exc).__name__
            return SpanExportResult.FAILURE


class WireSpanProcessor(SpanProcessor):
    """Keep span-start association; late ends must not enter a later SDK step."""
    def __init__(self, exporter):
        import threading
        self.exporter = exporter
        self.pending = {}
        self.lock = threading.Lock()

    def on_start(self, span, parent_context=None):
        key = (span.context.trace_id, span.context.span_id)
        with self.lock:
            if self.exporter.destination is None or len(self.pending) >= 20000:
                self.exporter.error = 'span_outside_transport_window'
            else:
                self.pending[key] = self.exporter.destination

    def on_end(self, span):
        key = (span.context.trace_id, span.context.span_id)
        with self.lock:
            destination = self.pending.pop(key, None)
        if destination is None or destination != self.exporter.destination:
            self.exporter.error = 'span_outside_transport_window'
            return
        self.exporter.export((span,))

    def force_flush(self, timeout_millis=30000):
        with self.lock:
            return not self.pending and self.exporter.error is None

    def shutdown(self):
        self.exporter.shutdown()

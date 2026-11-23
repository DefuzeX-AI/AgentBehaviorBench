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


"""Decode transported OTel spans without synthesizing new IDs or timestamps."""
from datetime import datetime
from opentelemetry.sdk.trace import ReadableSpan, Event
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, TraceFlags, TraceState, SpanKind, Status, StatusCode, Link


def context(value, flags=1):
    return SpanContext(int(value['trace_id'], 16), int(value['span_id'], 16),
                       is_remote=True, trace_flags=TraceFlags(flags), trace_state=TraceState())


def timestamp(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1_000_000_000)


class TransportedSpan(ReadableSpan):
    @property
    def dropped_attributes(self):
        return self.losses.get('dropped_attributes', 0)

    @property
    def dropped_events(self):
        return self.losses.get('dropped_events', 0)

    @property
    def dropped_links(self):
        return self.losses.get('dropped_links', 0)


def decode_span(row):
    identity = context(row['context'], row.get('trace_flags', 1))
    parent = None if row.get('parent_id') is None else SpanContext(
        identity.trace_id, int(row['parent_id'], 16), is_remote=True,
        trace_flags=identity.trace_flags, trace_state=TraceState())
    status = row.get('status', {})
    scope = row.get('scope')
    span = TransportedSpan(
        name=row['name'], context=identity, parent=parent,
        kind=SpanKind[row['kind'].split('.')[-1]],
        start_time=row['start_time_ns'], end_time=row['end_time_ns'],
        attributes=row.get('attributes') or {},
        events=[Event(e['name'], e.get('attributes') or {},
                      row['event_times_ns'][i] if 'event_times_ns' in row else timestamp(e['timestamp']))
                for i, e in enumerate(row.get('events', []))],
        links=[Link(context(e['context']), e.get('attributes') or {}) for e in row.get('links', [])],
        status=Status(StatusCode[status.get('status_code', 'UNSET')], status.get('description')),
        resource=Resource(row.get('resource', {}).get('attributes', {})),
        instrumentation_scope=InstrumentationScope(scope['name'], scope.get('version')) if scope else None)

    span.losses = {key: row.get(key, 0) for key in ('dropped_attributes', 'dropped_events', 'dropped_links')}
    return span

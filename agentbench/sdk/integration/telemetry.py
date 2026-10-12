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

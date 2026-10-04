"""Write ended spans immediately; complete payloads are stored separately."""
import json
import threading
from datetime import datetime, timezone
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from agentbench.observe.store import atomic_json, json_value, redact


class FileExporter(SpanExporter):
    def __init__(self, directory, run_id, session_id, secrets):
        self.directory, self.run_id, self.session_id = directory, run_id, session_id
        self.secrets = secrets
        self.lock = threading.Lock()
        self.error = None
        self.closed = False
        # Local correlation and payload paths belong to the ABB artifact, not
        # public OTel semantics consumed by SDK evidence/privacy validation.
        self.local_attributes = {}

    def annotate(self, span, attributes):
        with self.lock:
            self.local_attributes.setdefault(span.context.span_id, {}).update(attributes)

    def local(self, span, key):
        with self.lock:
            return self.local_attributes.get(span.context.span_id, {}).get(key)

    def export(self, spans, *, live=False):
        try:
            with self.lock:
                if self.closed:
                    return SpanExportResult.SUCCESS
                with (self.directory / ('otel-live.jsonl' if live else 'otel.jsonl')).open('a', encoding='utf-8') as stream:
                    for span in spans:
                        attributes = {**span.attributes, **self.local_attributes.get(span.context.span_id, {})}
                        if attributes.get('abb.invocation_id') != self.run_id:
                            continue
                        data = json.loads(span.to_json())
                        data['attributes'] = attributes
                        data['live'] = span.end_time is None
                        # Keep IDs explicit and stable for local UI and SDK comparisons.
                        data.update(trace_id=f'{span.context.trace_id:032x}',
                                    span_id=f'{span.context.span_id:016x}',
                                    parent_span_id=f'{span.parent.span_id:016x}' if span.parent else None,
                                    start_time_unix_nano=str(span.start_time),
                                    end_time_unix_nano=str(span.end_time))
                        data.update(dropped_attributes=span.dropped_attributes,
                                    dropped_events=span.dropped_events, dropped_links=span.dropped_links)
                        row = dict(schema='abb.observe.event.v1', source='otel', event='span',
                                   run_id=self.session_id, timestamp=data['end_time'], data=data)
                        stream.write(json.dumps(redact(row, self.secrets), ensure_ascii=False) + '\n')
                        if span.end_time is not None:
                            self.local_attributes.pop(span.context.span_id, None)
                    stream.flush()
            return SpanExportResult.SUCCESS
        except Exception as exc:
            self.error = type(exc).__name__
            return SpanExportResult.FAILURE

    def payload(self, span, label, value):
        name = f'{span.context.span_id:016x}-{label}.json'
        directory = self.directory / 'otel-payloads'
        directory.mkdir(exist_ok=True)
        atomic_json(directory / name, redact(json_value(value), self.secrets))
        self.annotate(span, {f'abb.{label}_ref': f'otel-payloads/{name}'})
        # Publish a real in-progress span snapshot; the ended export replaces it by ID.
        self.export([span], live=True)

    def event(self, span, event, value, *, span_event=True):
        """Persist full event data; optionally index a lifecycle event on the span."""
        directory = self.directory / 'otel-payloads'
        directory.mkdir(exist_ok=True)
        name = f'{span.context.span_id:016x}-events.jsonl'
        with (directory / name).open('a', encoding='utf-8') as stream:
            row = {'schema': 'abb.observe.event.v1', 'source': 'otel-payload',
                   'run_id': self.session_id, 'timestamp': datetime.now(timezone.utc).isoformat(),
                   'event': event, 'data': value}
            stream.write(json.dumps(redact(json_value(row), self.secrets), ensure_ascii=False) + '\n')
        self.annotate(span, {'abb.events_ref': f'otel-payloads/{name}'})
        if span_event:
            span.add_event(event)

    def shutdown(self):
        with self.lock:
            self.closed = True
            self.local_attributes.clear()

    def force_flush(self, timeout_millis=30000):
        return self.error is None

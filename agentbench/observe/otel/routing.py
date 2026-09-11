"""One bounded processor per provider, routing only to active file exporters."""
from threading import RLock
from weakref import WeakKeyDictionary
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, SimpleSpanProcessor

_routers = WeakKeyDictionary()
_lock = RLock()


class ExportRouter(SpanExporter):
    def __init__(self):
        self.exporters = set()
        self.lock = RLock()

    def export(self, spans):
        with self.lock:
            for exporter in self.exporters:
                exporter.export(spans)
        return SpanExportResult.SUCCESS

    def attach(self, exporter):
        with self.lock:
            self.exporters.add(exporter)

    def detach(self, exporter):
        with self.lock:
            self.exporters.discard(exporter)

    def shutdown(self):
        with self.lock:
            for exporter in self.exporters:
                exporter.shutdown()
            self.exporters.clear()


def attach(provider, exporter):
    with _lock:
        router = _routers.get(provider)
        if router is None:
            router = ExportRouter()
            provider.add_span_processor(SimpleSpanProcessor(router))
            _routers[provider] = router
        router.attach(exporter)
        return router

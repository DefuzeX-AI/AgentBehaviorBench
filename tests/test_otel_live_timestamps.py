import json
from opentelemetry.sdk.trace import TracerProvider
from agentbench.observe.otel.exporter import FileExporter


def test_live_and_final_timestamps(tmp_path):
    provider = TracerProvider()
    span = provider.get_tracer("test").start_span("invoke")
    exporter = FileExporter(tmp_path, "inv", "run", ())
    exporter.annotate(span, {"abb.invocation_id": "inv"})
    exporter.export([span], live=True)
    live = json.loads((tmp_path / "otel-live.jsonl").read_text())
    assert live["data"]["end_time_unix_nano"] is None
    assert live["data"]["end_time"] is None
    assert live["timestamp"] is not None
    span.end()
    exporter.export([span])
    final = json.loads((tmp_path / "otel.jsonl").read_text())
    assert final["data"]["span_id"] == live["data"]["span_id"]
    assert int(final["data"]["end_time_unix_nano"]) >= int(final["data"]["start_time_unix_nano"])
    assert final["timestamp"] == final["data"]["end_time"]

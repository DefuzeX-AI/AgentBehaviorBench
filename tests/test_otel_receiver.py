import gzip
import json
from urllib.request import Request, urlopen

import pytest

from agentbench.harness.otel import create_session
from agentbench.harness.otel.config import CaptureConfig
from agentbench.harness.otel.evidence import display_span


@pytest.mark.parametrize("transport", ["http/json", "http/protobuf", "grpc"])
def test_actual_exporters(tmp_path, transport):
    pytest.importorskip("opentelemetry.proto")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    session = create_session(CaptureConfig("native-otlp", protocol=transport), tmp_path, "example")
    try:
        if transport == "http/json":
            batch = {"resourceSpans": [{"scopeSpans": [{"scope": {"name": "test"}, "spans": [{
                "name": "read", "traceId": "12" * 16, "spanId": "34" * 8, "startTimeUnixNano": "12345678901",
                "attributes": [{"key": "api_key", "value": {"stringValue": "secret"}},
                               {"key": "messages", "value": {"arrayValue": {"values": [{"kvlistValue": {
                                   "values": [{"key": "content", "value": {"stringValue": "77"}}]}}]}}}]}]}]}]}
            request = Request(session.receiver.endpoint + "/v1/traces", gzip.compress(json.dumps(batch).encode()),
                              {"Content-Type": "application/json", "Content-Encoding": "gzip"})
            with urlopen(request) as response:
                assert response.status == 200
        else:
            if transport == "grpc":
                cls = pytest.importorskip("opentelemetry.exporter.otlp.proto.grpc.trace_exporter").OTLPSpanExporter
                exporter = cls(endpoint=session.receiver.endpoint, insecure=True)
            else:
                cls = pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter").OTLPSpanExporter
                exporter = cls(endpoint=session.receiver.endpoint + "/v1/traces")
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            with provider.get_tracer("test").start_as_current_span("read") as span:
                span.set_attribute("answer", "77")
                span.add_event("read complete")
                expected = f"{span.get_span_context().span_id:016x}"
            provider.shutdown()
    finally:
        session.close()
    row = json.loads((tmp_path / "spans.jsonl").read_text())
    data = display_span(row)
    assert data["origin"] == "agent_native" and data["scope"]["name"] == "test"
    if transport == "http/json":
        assert data["attributes"]["api_key"] == "[REDACTED]"
        assert data["attributes"]["messages"] == [{"content": "77"}]
        assert data["start_time_unix_nano"] == "12345678901"
    else:
        assert data["attributes"]["answer"] == "77" and data["span_id"] == expected
        assert data["events"][0]["name"] == "read complete"
    assert json.loads((tmp_path / "status.json").read_text())["span_count"] == 1


def test_chunked_node_exporter_request(tmp_path):
    from http.client import HTTPConnection
    from urllib.parse import urlsplit
    session = create_session(CaptureConfig("native-otlp"), tmp_path, "node")
    endpoint = urlsplit(session.receiver.endpoint)
    client = HTTPConnection(endpoint.hostname, endpoint.port, timeout=3)
    try:
        span = {"name": "read", "traceId": "12" * 16, "spanId": "34" * 8}
        batch = {"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}
        body = gzip.compress(json.dumps(batch).encode())
        client.request("POST", "/v1/traces", iter([body[:10], body[10:]]),
                       {"Content-Type": "application/json", "Content-Encoding": "gzip"}, encode_chunked=True)
        assert client.getresponse().status == 200
    finally:
        client.close()
        session.close()
    assert json.loads((tmp_path / "spans.jsonl").read_text())["span"]["spanId"] == span["spanId"]

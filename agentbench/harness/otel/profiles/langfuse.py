"""Local-only Langfuse tracing using its public callback and exporter interfaces."""
from uuid import uuid4


def local_client(endpoint, agent_id, capture_content):
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    # The SDK selects clients by public key. Isolate cases without cloud credentials.
    key = "pk-lf-abb-" + uuid4().hex
    provider = TracerProvider(resource=Resource.create({"service.name": agent_id}))
    client = Langfuse(public_key=key, secret_key="local-only", base_url=endpoint,
                      tracer_provider=provider, span_exporter=OTLPSpanExporter(endpoint=endpoint + "/v1/traces"),
                      mask=None if capture_content else lambda **kwargs: "[REDACTED]",
                      sample_rate=1.0)
    return client, CallbackHandler(public_key=key)

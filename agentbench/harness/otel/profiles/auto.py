"""Instrument the target runtime with maintained instrumentation libraries."""
from . import native


def environment(config, endpoint, agent_id):
    env = native.environment(config, endpoint, agent_id)
    if config.profile == "node-auto":
        env["NODE_OPTIONS"] = "--require=/opt/abb-otel/node/register.cjs"
        env.setdefault("OTEL_NODE_RESOURCE_DETECTORS", "env,process")
        env.setdefault("OTEL_BSP_SCHEDULE_DELAY", "200")
    elif config.profile == "python-auto":
        env["OPENINFERENCE_HIDE_INPUTS"] = env["OPENINFERENCE_HIDE_OUTPUTS"] = str(not config.capture_content).lower()
    elif config.profile == "java-auto":
        env["JAVA_TOOL_OPTIONS"] = "-javaagent:/opt/abb-otel/javaagent.jar"
    return env


def instrument_graph(endpoint, agent_id, capture_content=True):
    from openinference.instrumentation import TraceConfig
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(resource=Resource.create({"service.name": agent_id}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint + "/v1/traces")))
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(tracer_provider=provider, config=TraceConfig(
        hide_inputs=not capture_content, hide_outputs=not capture_content))
    return instrumentor, provider

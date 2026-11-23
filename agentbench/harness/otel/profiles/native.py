"""Point an upstream trace exporter at its Case-owned loopback receiver."""


def environment(config, endpoint, agent_id):
    env = dict(config.enable_env)
    trace_endpoint = endpoint if config.protocol == "grpc" else endpoint + "/v1/traces"
    env.update(OTEL_EXPORTER_OTLP_ENDPOINT=endpoint, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=trace_endpoint,
               OTEL_EXPORTER_OTLP_PROTOCOL=config.protocol, OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=config.protocol,
               OTEL_SERVICE_NAME=agent_id, OTEL_TRACES_EXPORTER="otlp", OTEL_TRACES_SAMPLER="always_on",
               OTEL_METRICS_EXPORTER="none", OTEL_LOGS_EXPORTER="none", ABB_OTEL_PROFILE=config.profile)
    env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = str(config.capture_content).lower()
    if config.endpoint_env:
        env[config.endpoint_env] = endpoint
    if config.profile in ('openclaw', 'opensoul'):
        import json
        from . import openclaw, opensoul
        patch = {}
        (openclaw if config.profile == 'openclaw' else opensoul).apply(patch, env)
        env['ABB_OTEL_GATEWAY_CONFIG'] = json.dumps(patch)
    return env

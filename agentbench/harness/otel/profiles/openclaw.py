"""OpenClaw diagnostics-otel gateway configuration."""
def apply(config, environment):
    if environment.get("ABB_OTEL_PROFILE") != "openclaw":
        return
    config.setdefault("plugins", {}).setdefault("entries", {}).setdefault("diagnostics-otel", {})["enabled"] = True
    config["diagnostics"] = {"enabled": True, "otel": {
        "enabled": True, "endpoint": environment["OTEL_EXPORTER_OTLP_ENDPOINT"],
        "protocol": "http/protobuf", "traces": True, "metrics": False,
        "logs": False, "sampleRate": 1, "captureContent": environment.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true") == "true",
    }}

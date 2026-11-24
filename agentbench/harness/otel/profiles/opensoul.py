"""Enable the pinned OpenSoul diagnostics plugin on its private gateway."""
def apply(config, environment):
    if environment.get("ABB_OTEL_PROFILE") != "opensoul":
        return
    config.setdefault("plugins", {}).setdefault("entries", {})["diagnostics-otel"] = {"enabled": True}
    config["diagnostics"] = {"enabled": True, "otel": {
        "enabled": True, "endpoint": environment["OTEL_EXPORTER_OTLP_ENDPOINT"],
        "protocol": "http/protobuf", "traces": True, "metrics": False, "logs": False,
        "sampleRate": 1,
    }}

def exporter_error(path, secrets):
    """Read the Gateway's own plugin startup diagnostic after it closes."""
    from agentbench.observe.store import redact
    if not path.is_file():
        return None
    marker = "plugin service failed (diagnostics-otel):"
    with path.open(encoding="utf-8", errors="replace") as log:
        for line in log:
            _, found, detail = line.partition(marker)
            if found:
                return redact(found + " " + detail.strip(), secrets)[:500]
    return None

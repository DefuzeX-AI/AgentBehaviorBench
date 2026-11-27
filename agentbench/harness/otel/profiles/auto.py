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

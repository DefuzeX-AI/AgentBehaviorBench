"""Install source-injected worker dependencies in the image's Python environment."""
import re


def stage_runtime_dependencies(context, dockerfile):
    source = dockerfile.read_text(encoding='utf-8')
    users = re.findall(r'(?im)^USER\s+(.+)$', source)
    if not users or users[-1].strip() in ('root', '0', '0:0'):
        raise ValueError('Runtime overlay requires an explicit non-root image USER')
    requirements = '.abb-runtime/agentbench/runtime/docker/requirements.txt'
    if not (context / requirements).is_file():
        raise ValueError('Injected runtime requirements are missing')
    # Use the final stage's PATH, including an Agent-selected virtual environment.
    # pip evaluates Python markers here, never against the host's interpreter.
    dockerfile.write_text(source + '\nUSER root\n'
        f'COPY {requirements} /opt/abb-runtime-deps/requirements.txt\n'
        'RUN python -m pip --version >/dev/null 2>&1 || python -m ensurepip --default-pip\n'
        'RUN python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple '
        '-r /opt/abb-runtime-deps/requirements.txt\nUSER ' + users[-1] + '\n', encoding='utf-8')


def stage_otel_dependencies(dockerfile, config):
    """Install only the receiver and instrumentation needed by this target."""
    from agentbench.harness.otel.config import tomllib
    from pathlib import Path
    profile = getattr(getattr(config, "otel", None), "profile", "unconfigured")
    if profile in ("unconfigured", "unsupported", "file-export"):
        return
    source = dockerfile.read_text(encoding="utf-8")
    user = re.findall(r"(?im)^USER\s+(.+)$", source)[-1]
    base = ".abb-runtime/agentbench/harness/otel/assets"
    deps = "opentelemetry-proto>=1.30,<2"
    lines = ["USER root", f"RUN python -m pip install --no-cache-dir '{deps}'"]
    if config.otel.protocol == "grpc":
        lines += ["RUN python -m pip install --no-cache-dir 'grpcio>=1.60,<2'"]
    if profile == "openclaw":
        descriptor = Path(__file__).resolve().parents[2] / "harness/otel/assets/openclaw/plugin.toml"
        with descriptor.open("rb") as stream:
            plugin = tomllib.load(stream)
        spec = plugin["package"] + "@" + plugin["version"]
        lines += ["RUN mkdir -p /opt/abb-otel/openclaw && chown " + user + " /opt/abb-otel/openclaw",
                  "USER " + user,
                  f"RUN test \"$(npm view {spec} dist.integrity)\" = '{plugin['integrity']}'"
                  f" && HOME=/opt/abb-otel/openclaw openclaw plugins install npm:{spec} --pin --accept-capabilities",
                  "USER root"]
    if profile == "python-auto":
        lines += [f"COPY {base}/python/requirements.txt /opt/abb-otel/python.txt",
                  "RUN python -m pip install --no-cache-dir -r /opt/abb-otel/python.txt"]
    elif profile == "node-auto":
        lines += [f"COPY {base}/node/ /opt/abb-otel/node/",
                  "RUN npm ci --prefix /opt/abb-otel/node --ignore-scripts --no-audit --no-fund"]
    elif profile == "java-auto":
        descriptor = Path(__file__).resolve().parents[2] / "harness/otel/assets/java/agent.toml"
        with descriptor.open("rb") as stream:
            artifact = tomllib.load(stream)
        lines += ["RUN mkdir -p /opt/abb-otel && curl -fsSL '" + artifact["url"] +
                  "' -o /opt/abb-otel/javaagent.jar && echo '" + artifact["sha256"] +
                  "  /opt/abb-otel/javaagent.jar' | sha256sum -c -"]
    lines.append("USER " + user)
    dockerfile.write_text(source + "\n" + "\n".join(lines) + "\n", encoding="utf-8")

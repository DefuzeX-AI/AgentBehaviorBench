FROM golang:1.27.4-bookworm AS builder
WORKDIR /build
COPY agent/ ./
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    go build -trimpath -tags no_audio -o docker-agent .

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent
WORKDIR /opt/agent
COPY --from=builder /build/docker-agent /usr/local/bin/docker-agent
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10001 agent && \
    mkdir -p /workspace /home/agent/.config/cagent && \
    chown -R agent:agent /workspace /home/agent
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' 'PyYAML>=6,<7'
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml
COPY bootstrap/ ./bootstrap/
COPY --from=builder /build/pkg/config/sources/builtin-agents/default.yaml ./bootstrap/upstream-default.yaml
RUN python bootstrap/build_config.py
USER agent
RUN docker-agent serve acp --help >/dev/null && python -c "import opentelemetry.sdk.trace, jsonschema, dotenv"

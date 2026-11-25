FROM oven/bun:1.3.11 AS bun_runtime
FROM python:3.12-slim-bookworm AS dependencies
COPY --from=bun_runtime /usr/local/bin/bun /usr/local/bin/bun
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep build-essential unzip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
WORKDIR /opt/agent/agent/openteams-cli
COPY agent/openteams-cli/ ./
RUN HUSKY=0 bun install --frozen-lockfile \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
RUN chown agent:agent /home/agent
USER agent

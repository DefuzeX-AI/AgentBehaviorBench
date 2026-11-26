FROM oven/bun:latest AS bun-runtime
FROM python:3.12-slim-bookworm AS dependencies
COPY --from=bun-runtime /usr/local/bin/bun /usr/local/bin/bun
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && useradd --create-home --uid 10001 agent
COPY agent/cli/ /opt/agent/agent/cli/
COPY agent/shared/ /opt/agent/agent/shared/
WORKDIR /opt/agent/agent/cli
RUN bun install --frozen-lockfile \
    && ln -s cli/node_modules /opt/agent/agent/node_modules \
    && chown -R agent:agent /home/agent/.bun
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent /workspace && chown agent:agent /home/agent /workspace
USER agent

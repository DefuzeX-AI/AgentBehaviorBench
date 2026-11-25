FROM golang:1.25.8-bookworm AS golang
FROM node:24-bookworm-slim AS dependencies
COPY --from=golang /usr/local/go/ /usr/local/go/
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git build-essential ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:/usr/local/go/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN TAU_SKIP_OLLAMA_PREPULL=1 npm ci && npm run build \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

FROM node:22-bookworm-slim AS dependencies
ENV ONNXRUNTIME_NODE_INSTALL_CUDA=skip PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PATH=/opt/python/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/python \
    && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' httpx 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN CI=1 npm ci && SWARMCLAW_BUILD_MODE=1 npm run build:ci \
    && cp -r public .next/standalone/public \
    && mkdir -p .next/standalone/.next && cp -r .next/static .next/standalone/.next/static \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
RUN chown agent:agent /home/agent
USER agent

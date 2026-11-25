FROM node:24-bookworm-slim AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git build-essential ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN npm install -g opencode-ai@1.18.2 && npm ci && npm run build \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
USER agent
RUN node bin/takt install opencode \
    && node --input-type=module -e "import { inspectProviderInstallation } from './dist/infra/managed-providers/loader.js'; const state = await inspectProviderInstallation('opencode'); if (state.state !== 'ready') throw new Error('Native managed OpenCode integrity check failed');"
USER root
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

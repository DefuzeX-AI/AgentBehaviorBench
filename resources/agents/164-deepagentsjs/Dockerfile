FROM node:24-bookworm-slim AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git build-essential \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && npm install -g pnpm@10.29.2 && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pnpm install --frozen-lockfile && pnpm --filter deepagents-acp... build \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

FROM node:24-bookworm-slim AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PATH=/opt/python/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git chromium \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/python \
    && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' httpx 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN npm install --global npm@11.19.0 && npm ci && npm run backend:bundle \
    && npm run build -- --filter=@pizza-bot/cli... \
    && node --input-type=module -e 'await import("@pizza-bot/core"); await import("@pizza-bot/logging");' \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
RUN chown agent:agent /home/agent
USER agent

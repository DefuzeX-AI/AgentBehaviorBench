FROM node:22-bookworm-slim AS node
FROM python:3.11-slim-bookworm AS dependencies
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv && npm install -g mcp-remote
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv pip install --system --require-hashes -r requirements.lock \
    && pip install --no-cache-dir opentelemetry-sdk 'jsonschema>=4.23,<5' \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown -R agent:agent /opt/agent/agent /workspace /home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

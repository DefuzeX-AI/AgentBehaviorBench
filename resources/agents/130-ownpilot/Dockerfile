FROM node:22-bookworm-slim AS node
FROM postgres:16-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && apt-get update && apt-get install -y --no-install-recommends \
       python3 python3-venv build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && npm install --global pnpm@10.29.3
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent NODE_ENV=production
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && NODE_ENV=development pnpm install --frozen-lockfile \
    && pnpm --filter @ownpilot/cli... build
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' 'PyYAML>=6,<7' 'filelock>=3.32.7,<4' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace /home/agent/.local/share/ownpilot \
    && chown -R agent:agent /home/agent \
    && chown agent:agent /opt/agent/agent/packages/core/data/providers/abb-runtime.json
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
COPY agent.toml ./agent.toml
USER agent

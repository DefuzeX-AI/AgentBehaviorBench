FROM node:22-bookworm-slim AS node
FROM pgvector/pgvector:pg16-bookworm AS dependencies
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git redis-server \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk 'langchain-core>=1,<2'
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN npm ci --prefix backend && npm ci --prefix bff && npm run build --prefix bff \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown -R agent:agent /opt/agent/agent /workspace /home/agent
FROM dependencies
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
ENTRYPOINT []
CMD []

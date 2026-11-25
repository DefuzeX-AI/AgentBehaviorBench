FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g @modelcontextprotocol/server-filesystem
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir -r requirements.txt 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'mypy-extensions>=1,<2'
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    PUPPETEER_EXECUTABLE_PATH=/opt/agent/bootstrap/chromium PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential chromium fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g chrome-devtools-mcp
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir . 'agent-client-protocol>=0.7,<1' opentelemetry-sdk jsonschema \
    && playwright install --with-deps chromium
RUN cd webqa_agent && npm install
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN chmod +x /opt/agent/bootstrap/chromium \
    && mkdir -p /workspace && chown -R agent:agent /workspace /opt/agent/agent
USER agent

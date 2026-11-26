FROM denoland/deno:debian AS deno_runtime
FROM python:3.12-slim-bookworm AS dependencies
COPY --from=deno_runtime /usr/bin/deno /usr/local/bin/deno
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent DENO_DIR=/home/agent/deno-cache
RUN apt-get update && apt-get install -y --no-install-recommends git curl unzip build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir httpx 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN mkdir -p data node_modules debug_logs /home/agent/deno-cache \
    && touch .noupdate \
    && chown agent:agent data node_modules debug_logs /home/agent /home/agent/deno-cache
USER agent
RUN deno cache src/server/index.mjs \
    src/public/parts/shells/ideIntegration/public/fount_ide_agent.mjs \
    src/public/parts/shells/ideIntegration/main.mjs \
    src/public/parts/shells/serviceSourceManage/main.mjs \
    default/templates/user/chars/ZL-31/main.mjs \
    src/public/parts/serviceGenerators/AI/proxy/main.mjs \
    src/public/parts/plugins/code-execution/main.mjs \
    src/public/parts/plugins/file-operations/main.mjs \
    src/public/parts/plugins/char-writing/main.mjs \
    src/public/parts/plugins/web-search/main.mjs \
    src/public/parts/plugins/web-browse/main.mjs \
    src/public/parts/plugins/browser-integration/main.mjs \
    src/public/parts/plugins/timer/main.mjs \
    src/public/parts/plugins/fount-api/main.mjs \
    src/public/parts/plugins/sub-agent/main.mjs \
    src/public/parts/plugins/context-compress/main.mjs \
    src/public/parts/plugins/async-task/main.mjs
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime

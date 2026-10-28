# Build the original pinned source with its workspace lock and native build.
FROM node:24.21.0-bookworm-slim
RUN npm install --global pnpm@10.23.0 \
    && apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip git build-essential ripgrep chromium \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent \
    BITTERBOT_ORCHESTRATOR_INSTALL_DIR=/opt/agent/agent/orchestrator/target/release
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && pnpm install --frozen-lockfile && pnpm build \
    && node bitterbot.mjs --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY bootstrap/ ./bootstrap/
COPY embedding-model.json ./
RUN python /opt/agent/bootstrap/download_embedding.py
# Jiti's cold plugin-SDK transpilation exceeds the default runtime heap. Retain
# only its native compiled-source cache, with no network/model/Case execution.
ENV TMPDIR=/home/agent/.cache/bitterbot
RUN --network=none mkdir -p "$TMPDIR" \
    && python /opt/agent/bootstrap/warm_cache.py \
    && chown -R agent:agent /home/agent/.cache
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
USER agent

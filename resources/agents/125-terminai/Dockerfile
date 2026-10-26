FROM node:22-bookworm-slim AS builder

WORKDIR /src
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3 \
    make \
    g++ \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/Prof-Harita/terminaI.git . \
    && git checkout 4b816c7acc5a89afb692d512c046cdc61bf6186b

RUN npm install --legacy-peer-deps
RUN npm run build --workspace=@terminai/microvm
RUN sed -i 's|import { createRequire } from "node:module";|/* import createRequire */|' bundle/gemini.js \
    && sed -i 's|if (this.clientCapabilities?.fs) {|if (this.clientCapabilities?.fs \&\& process.env.TERMINAI_USE_ACP_FS === "true") {|' bundle/gemini.js

FROM node:22-bookworm-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    ca-certificates \
    curl \
    git \
    ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        'agent-client-protocol==0.12.1' \
        'filelock>=3.32.7,<4' \
        'PyYAML>=6,<7' \
        'opentelemetry-sdk>=1.30,<2' \
        'jsonschema>=4.23,<5' \
        'python-dotenv>=1,<2' \
        'pytest'

WORKDIR /opt/agent

RUN usermod -l agent node \
    && groupmod -n agent node \
    && usermod -d /home/agent -m agent \
    && mkdir -p /home/agent/workspace \
    && mkdir -p /opt/terminai/node_modules/@terminai \
    && chown -R agent:agent /home/agent /opt/agent /opt/terminai

COPY --from=builder --chown=agent:agent /src/bundle /opt/terminai/bundle
COPY --from=builder --chown=agent:agent /src/package.json /opt/terminai/
COPY --from=builder --chown=agent:agent /src/packages/microvm /opt/terminai/node_modules/@terminai/microvm

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/

ENV PATH="/opt/venv/bin:/opt/terminai:$PATH" \
    PYTHONPATH="/opt/abb-runtime:/opt/agent" \
    NODE_PATH="/opt/terminai/node_modules" \
    PYTHONUNBUFFERED=1 \
    NODE_OPTIONS="--max-old-space-size=1536" \
    HOME="/home/agent"

USER agent

# Native release packaging; no source patches or replacement Agent loop.
# Base digest and package-manager integrity pin come from the pinned upstream.
FROM docker.io/library/node:22-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 make g++ git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/qwen-source
COPY agent/ ./
RUN QWEN_SKIP_PREPARE=1 corepack pnpm install --frozen-lockfile --reporter=append-only \
    && npm run build -- --cli-only \
    && npm run bundle \
    && npm run prepare:package \
    && cd dist && npm pack

FROM docker.io/library/node:22-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-venv python3-pip git ripgrep jq curl ca-certificates procps \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
COPY --from=builder /opt/qwen-source/dist/*.tgz /tmp/
RUN npm install -g /tmp/*.tgz && npm cache clean --force && rm -f /tmp/*.tgz \
    && python -m pip install --no-cache-dir \
       'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
WORKDIR /opt/agent
# ABB stages this directory and installs the pinned ACP/SDK dependencies.
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml source-manifest.json ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

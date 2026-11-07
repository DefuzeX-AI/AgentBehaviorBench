# Install the pinned oh-my-pi (omp) release and the Bun runtime it requires from one integrity-checked npm lock.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep fd-find \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY bootstrap/list_providers.ts /tmp/list_providers.ts
# Dependency install scripts are skipped (onnxruntime-node, an optional dependency
# of an unused local-embedding feature, would download binaries). The only script
# omp needs is bun's postinstall, which copies the Bun binary out of the locked
# @oven/bun-linux-* package without network access; run it explicitly.
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force \
    && node node_modules/bun/install.js \
    && bun --version \
    && HOME=/tmp/omp-build-check bun node_modules/@oh-my-pi/pi-coding-agent/dist/cli.js --version \
    && cp /tmp/list_providers.ts ./list_providers.ts \
    && HOME=/tmp/omp-build-check bun list_providers.ts > /opt/agent/builtin-providers.json \
    && rm -rf /tmp/omp-build-check list_providers.ts /tmp/list_providers.ts \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Headless Chromium for the browser tool. abb-chromium imports the interceptor CA into
# Chromium's NSS store before launch; zz-abb-lean keeps Chromium within the container's
# pid budget (#158).
USER root
RUN apt-get update && apt-get install -y --no-install-recommends chromium libnss3-tools fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY abb-chromium /usr/local/bin/abb-chromium
RUN chmod 755 /usr/local/bin/abb-chromium
COPY zz-abb-lean /etc/chromium.d/zz-abb-lean
USER agent

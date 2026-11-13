# Build the selected upstream commit from its own pnpm lockfile. Only mastracode and
# its workspace dependencies (plus the workspace root, which provides turbo) are
# installed; `turbo build --filter ./mastracode/tui` is upstream's `build:mastracode`.
# The workspace packages are then linked where the published install puts them, so
# bootstrap/launch.py and abb-acp-browser.mjs resolve mastracode and @mastra/code-sdk
# from /opt/agent/agent/node_modules exactly as in the default image.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# The global virtual store is disabled so node_modules stays inside the image tree
# instead of linking into a per-user store; the same settings reach the pnpm runs that
# turbo starts. pnpm's pre-run dependency check is off because only the filtered
# subset is installed. turbo concurrency and the Node heap are capped to fit a shared
# 8 GB Docker VM.
# corepack provides the pnpm version (and checks its hash) pinned in packageManager.
RUN corepack enable \
    && export CI=true TURBO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
       pnpm_config_enable_global_virtual_store=false npm_config_enable_global_virtual_store=false \
       pnpm_config_verify_deps_before_run=false npm_config_verify_deps_before_run=false \
    && cd agent && pnpm --version \
    && pnpm install --frozen-lockfile --config.enable-global-virtual-store=false \
       --store-dir /tmp/pnpm-store --filter "mastracode..." --filter mastra-turbo \
    && rm -rf /tmp/pnpm-store \
    && NODE_OPTIONS=--max-old-space-size=3072 node_modules/.bin/turbo build \
       --filter ./mastracode/tui --concurrency=2 \
    && rm -rf .turbo node_modules/.cache \
    && mkdir -p node_modules/@mastra node_modules/.bin \
    && ln -sfn ../../mastracode/sdk node_modules/@mastra/code-sdk \
    && ln -sfn ../mastracode/tui node_modules/mastracode \
    && ln -sfn ../mastracode/dist/cli.js node_modules/.bin/mastracode \
    && node node_modules/mastracode/dist/cli.js --help > /dev/null \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY provenance.json ./provenance.json
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

# `mastracode --acp` ignores the browser setting (only the TUI creates the browser);
# this entry is upstream's acpMain plus the settings.json browser.
COPY bootstrap/abb-acp-browser.mjs ./agent/abb-acp-browser.mjs

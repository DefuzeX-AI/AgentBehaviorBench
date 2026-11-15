# Build the selected upstream commit of the mastra monorepo with its own pnpm
# (corepack, `packageManager`) and lockfile, limited to the `mastracode` CLI
# (mastracode/tui) and its workspace dependencies, using upstream's own build task
# (`pnpm build:mastracode` = `turbo build --filter ./mastracode/tui`).
# The release image resolves `mastracode` and `@mastra/code-sdk` from
# agent/node_modules; the same two names are linked there to the built workspace
# packages, so bootstrap/launch.py and abb-acp-browser.mjs run unchanged.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent HUSKY=0 COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    TURBO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 \
    pnpm_config_enable_global_virtual_store=false npm_config_enable_global_virtual_store=false \
    pnpm_config_store_dir=/opt/pnpm-store
WORKDIR /opt/agent
COPY agent/ ./agent/
# The global virtual store would link packages into the build user's home; it is
# switched off so every dependency lives under /opt/agent/agent and is readable by
# the unprivileged runtime user. The frozen lockfile pins every version and integrity;
# the workspace's registry-age/trust gates (minimumReleaseAge, trustPolicy) re-query
# metadata for every entry and depend on today's date, so they are switched off to
# install the commit's lockfile exactly as it was accepted upstream.
RUN cd agent && corepack enable \
    && pnpm install --frozen-lockfile --filter 'mastracode...' --filter mastra-turbo \
         --config.trust-policy=off --config.minimum-release-age=0 --fetch-timeout=600000 --network-concurrency=8 --child-concurrency=2 \
    && NODE_OPTIONS=--max-old-space-size=4096 pnpm turbo build --filter ./mastracode/tui --concurrency=2 \
    && mkdir -p node_modules/.bin node_modules/@mastra \
    && chmod 755 mastracode/tui/dist/cli.js \
    && ln -sfn ../../mastracode/tui/dist/cli.js node_modules/.bin/mastracode \
    && ln -sfn ../../mastracode/sdk node_modules/@mastra/code-sdk \
    && if find mastracode/tui/node_modules mastracode/sdk/node_modules -maxdepth 2 -type l -exec readlink -f {} + \
          | grep -v '^/opt/agent/agent/'; then echo 'dependency links leave the unit' >&2; exit 1; fi \
    && node node_modules/.bin/mastracode --help > /dev/null \
    && node --input-type=module -e "await import('@mastra/code-sdk'); await import('@mastra/code-sdk/acp/server'); await import('@mastra/code-sdk/onboarding/settings')" \
    && rm -rf /opt/pnpm-store /root/.cache /root/.local/share/pnpm \
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

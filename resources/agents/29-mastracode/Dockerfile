# Install the pinned mastracode CLI from an integrity-checked npm lock; its ACP server (`mastracode --acp`) is built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && npm ci --omit=dev --no-audit --no-fund && npm cache clean --force \
    && node node_modules/mastracode/dist/cli.js --help > /dev/null \
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

# `mastracode --acp` ignores the browser setting (only the TUI creates the browser);
# this entry is upstream's acpMain plus the settings.json browser.
COPY bootstrap/abb-acp-browser.mjs ./agent/abb-acp-browser.mjs

# Install the pinned OpenClaw release from its integrity-checked npm lock; the Gateway and ACP bridge are built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Dependency install scripts (native prebuild fetchers) are skipped. OpenClaw's own
# pre/postinstall only prune and finalize its package dir; the launcher replays them
# on first run, so run it once here while node_modules is still writable (the
# runtime uid cannot write /opt/agent). The marker check fails the build otherwise.
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force \
    && node node_modules/openclaw/openclaw.mjs --version \
    && test ! -e node_modules/openclaw/.openclaw-lifecycle-pending \
    && test ! -e node_modules/openclaw/dist/openclaw-install-guard \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

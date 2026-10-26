# Build the pinned OpenSoul source (NJX-njx/opensoul) and expose its headless
# Gateway + ACP bridge. bootstrap/launch.py starts the Gateway, then execs the
# ACP bridge (opensoul acp), which forwards prompts over the local WebSocket.
#
# The install layer requires the full workspace (packages/* and extensions/* are
# link: importers in the frozen lockfile), so the source is copied before
# `pnpm install`. The heavy platform trees (apps/, publish/, assets/, Swabble/,
# docs/) are excluded by .dockerignore, keeping the build context small.
FROM node:22-bookworm

# Python for the ABB runtime worker and the ACP launch script.
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent

RUN corepack enable
WORKDIR /opt/agent

COPY agent/ ./

RUN pnpm install --frozen-lockfile \
    && OPENSOUL_A2UI_SKIP_MISSING=1 pnpm build \
    && node patch-acp-final.mjs

ENV NODE_ENV=production

RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

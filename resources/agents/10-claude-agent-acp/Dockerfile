# Build the pinned Claude ACP bridge and its bundled Claude Agent SDK runtime.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && npm install -g pnpm@9.12.0
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent CLAUDE_CONFIG_DIR=/home/agent/.claude \
    CLAUDE_AGENT_LOGS=/home/agent/.claude/logs \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1 NO_BROWSER=1
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY bootstrap/ ./bootstrap/
RUN python bootstrap/patch_source.py agent/src/session-titles.ts \
    && cd agent && npm ci && npm run build \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace /home/agent/.claude/logs \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
USER agent

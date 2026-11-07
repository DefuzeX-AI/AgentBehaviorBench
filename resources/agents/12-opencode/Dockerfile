# Install the pinned OpenCode release from its integrity-checked npm lock; its ACP server is built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Scripts are skipped so the install does not depend on the npm version's script
# policy; opencode-ai's own postinstall is then run explicitly. It only links the
# platform binary from the locked opencode-linux-x64[-baseline] package.
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force \
    && node node_modules/opencode-ai/postinstall.mjs && ./node_modules/.bin/opencode --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

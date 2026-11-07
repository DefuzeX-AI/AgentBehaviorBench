# Install the pinned LLxprt Code release from its integrity-checked npm lock; its ACP
# server (`llxprt --experimental-acp`) is built in. The package requires Node >= 24 and
# runs its prebuilt bundle on the Bun runtime shipped as an npm dependency.
FROM node:24-bookworm
# ripgrep is preinstalled so LLxprt's search tool can use a local rg binary.
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Install scripts stay enabled: the bundled Bun runtime, node-pty and the tree-sitter /
# ast-grep grammars set up their native parts at install time.
RUN cd agent && npm ci --omit=dev --no-audit --no-fund && npm cache clean --force \
    && node node_modules/@vybestack/llxprt-code/bin/llxprt.mjs --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

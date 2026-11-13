# Build the selected upstream commit from its own npm lockfile the way the release
# workflow does (`npm ci`, `npm run build:packages`, then the CLI package's prepack
# bundle). The npm workspace links node_modules/@vybestack/llxprt-code to
# packages/cli, so bootstrap/launch.py starts the same bin/llxprt.mjs shim, which
# runs bundle/llxprt.js on the Bun runtime installed from the lock. The shim looks
# for Bun in the package's own node_modules (or an enclosing node_modules); npm hoists
# the CLI's `bun` dependency to the workspace root, so it is linked back there.
FROM node:24-bookworm
# ripgrep is preinstalled so LLxprt's search tool can use a local rg binary.
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Install scripts stay enabled: the Bun runtime, node-pty, the tree-sitter / ast-grep
# grammars and the patch-package postinstall set up their parts at install time.
RUN cd agent && npm ci --no-audit --no-fund \
    && NODE_OPTIONS=--max-old-space-size=4096 npm run build:packages \
    && (cd packages/cli && npm run prepack) \
    && test -f packages/cli/bundle/llxprt.js \
    && mkdir -p packages/cli/node_modules \
    && ln -sfn ../../../node_modules/bun packages/cli/node_modules/bun \
    && npm cache clean --force \
    && node node_modules/@vybestack/llxprt-code/bin/llxprt.mjs --version \
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

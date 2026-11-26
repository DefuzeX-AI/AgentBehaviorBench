# Build the selected upstream commit from its own npm workspace lockfile. The
# workspace links agent/node_modules/@vybestack/llxprt-code to packages/cli, so the
# published `llxprt` bin (bin/llxprt.mjs) that bootstrap/launch.py execs is the same
# path as in the release install. The CLI bundle (bundle/llxprt.js, what the npm
# release ships) is built with the repo's pinned Bun; the shim falls back to
# packages/cli/index.ts when a revision has no bundle step.
# The shim looks for Bun in <package>/node_modules/bun or an enclosing node_modules;
# in the release that is the hoisted dependency, but in the workspace packages/cli
# is not under node_modules (and bun's postinstall moves the @oven binary), so the
# root's installed bun is linked as packages/cli's own dependency.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent HUSKY=0
WORKDIR /opt/agent
COPY agent/ ./agent/
# Install scripts stay enabled: Bun, node-pty and the tree-sitter / ast-grep grammars
# set up their native parts at install time, and the root postinstall applies patches/.
RUN cd agent && npm ci --no-audit --no-fund \
    && if grep -q '"generate"' package.json; then npm run generate; fi \
    && if [ -f scripts/bun-build.config.ts ]; then node_modules/.bin/bun scripts/bun-build.config.ts --cli-only; fi \
    && test -e node_modules/@vybestack/llxprt-code/bin/llxprt.mjs \
    && if [ ! -e packages/cli/node_modules/bun ] && [ -d node_modules/bun ]; then \
         mkdir -p packages/cli/node_modules && ln -s ../../../node_modules/bun packages/cli/node_modules/bun; fi \
    && node node_modules/@vybestack/llxprt-code/bin/llxprt.mjs --version \
    && npm cache clean --force \
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

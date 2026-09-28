# Install the pinned Kode CLI release (with its built-in kode-acp ACP server) from an integrity-checked npm lock.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Install scripts are skipped: Kode's postinstall only tries to download a native
# binary from GitHub Releases and falls back to the Node.js entry point, which is
# what the launcher runs; @vscode/ripgrep's postinstall would also download, and
# Kode prefers the system `rg` installed above.
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund && npm cache clean --force \
    && test -f node_modules/@shareai-lab/kode/dist/index.js \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

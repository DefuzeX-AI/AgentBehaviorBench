# Install the pinned Codewhale release from its integrity-checked npm lock. The
# native ACP server (`codewhale serve --acp`) ships inside the single Rust
# binary, which the package's own installer downloads and checksum-verifies
# against the release's codewhale-artifacts-sha256.txt.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Scripts are skipped so the install does not depend on the npm version's script
# policy; codewhale's installer is then run explicitly. Its npm postinstall is
# the fail-fast `--optional` form (15 s, one attempt) and can silently defer the
# binary to first launch, which the agent container cannot download, so the
# checksum-verifying non-optional form is what must succeed here.
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && node node_modules/codewhale/scripts/install.js \
    && ./node_modules/.bin/codewhale --version \
    && npm cache clean --force \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

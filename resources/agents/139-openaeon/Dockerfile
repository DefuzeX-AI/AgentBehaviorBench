FROM node:24-bookworm-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205
RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Pipeline-Depth=0 update && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=2 -o Acquire::http::Pipeline-Depth=0 install -y --no-install-recommends python3-venv git build-essential pkg-config ca-certificates curl && rm -rf /var/lib/apt/lists/*
RUN npm install -g pnpm@10.23.0 --fetch-retries=0 --fetch-timeout=20000
ENV NODE_OPTIONS=--max-old-space-size=2048
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN --mount=type=cache,id=abb-openaeon-pnpm,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile --network-concurrency=4 --fetch-retries=1 --fetch-timeout=20000
RUN pnpm build
RUN node openaeon.mjs --version && node openaeon.mjs acp --help && node openaeon.mjs gateway --help

COPY bootstrap/launch.py bootstrap/warm_cache.py /opt/agent/bootstrap/
RUN useradd --create-home --uid 10001 agent && mkdir -p /opt/openaeon-node-cache /opt/openaeon-jiti-cache && chown agent:agent /opt/openaeon-node-cache /opt/openaeon-jiti-cache
USER agent
RUN --network=none python3 /opt/agent/bootstrap/warm_cache.py && chmod -R a+rX /opt/openaeon-node-cache /opt/openaeon-jiti-cache
USER root

RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir 'agent-client-protocol==0.12.1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
RUN mkdir -p /workspace/project && chown -R agent:agent /workspace /home/agent
USER agent

FROM node:22-bookworm-slim
RUN apt-get -o Acquire::Retries=2 update && apt-get install -y --no-install-recommends python3-venv git ripgrep ca-certificates && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# Install official published JS/Kotlin artifacts without executing package lifecycle scripts.
RUN --mount=type=cache,target=/root/.npm cd agent && npm ci --ignore-scripts --no-audit --no-fund --maxsockets=4 && node node_modules/@xiuper/cli/dist/jsMain/typescript/index.js --help
RUN python -m pip install --no-cache-dir 'agent-client-protocol==0.12.1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

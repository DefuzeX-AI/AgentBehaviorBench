FROM node:24-bookworm-slim
# Bootstrap ca-certificates over Debian's GPG-verified HTTP repository; slim Node has no CA bundle yet.
RUN apt-get -o Acquire::Retries=2 update && apt-get -o Acquire::Retries=2 install -y --no-install-recommends python3-venv git ripgrep ca-certificates bubblewrap socat && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN --mount=type=cache,target=/root/.npm cd agent && npm ci --cache /root/.npm --ignore-scripts --no-audit --no-fund --fetch-retries=2 --fetch-timeout=60000 --maxsockets=4 && npm run build
RUN python -m pip install --no-cache-dir 'agent-client-protocol==0.12.1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

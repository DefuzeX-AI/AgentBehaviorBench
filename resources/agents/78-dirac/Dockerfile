# The published package contains the native ACP server and bundled runtime assets.
# Node 24 is within Dirac 0.5.23's declared >=22.13.0 <25.0.0 engine range.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && ./node_modules/.bin/dirac --version \
    && npm cache clean --force \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
USER agent

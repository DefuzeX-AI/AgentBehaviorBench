# Build the pinned source with its own frozen pnpm lock and integrity checks.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && npm install -g pnpm@9.12.0
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent MINIMAX_DATA_DIR=/home/agent/.minimax \
    MCODE_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && pnpm install --frozen-lockfile && pnpm build \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Headless Chromium for the browser tool. abb-chromium imports the interceptor CA into
# Chromium's NSS store before launch; zz-abb-lean keeps Chromium within the container's
# pid budget (#158).
USER root
RUN apt-get update && apt-get install -y --no-install-recommends chromium libnss3-tools fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY abb-chromium /usr/local/bin/abb-chromium
RUN chmod 755 /usr/local/bin/abb-chromium
COPY zz-abb-lean /etc/chromium.d/zz-abb-lean
USER agent

FROM node:24-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git build-essential ca-certificates     && rm -rf /var/lib/apt/lists/*     && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'     && npm install -g pnpm@10.33.0
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pnpm install --frozen-lockfile     && pnpm run build:packages     && pnpm -C apps/kimi-code run build     && useradd --create-home --uid 10001 agent     && mkdir /workspace && chown agent:agent /workspace
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV npm_config_cache=/home/agent/.npm-runtime
RUN mkdir -p /home/agent && chown agent:agent /home/agent
USER agent

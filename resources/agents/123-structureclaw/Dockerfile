FROM node:24-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PATH=/opt/venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git libgomp1 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN npm ci --prefix backend && npm run db:generate --prefix backend && npm run build --prefix backend \
    && pip install --no-cache-dir -r backend/src/agent-skills/analysis/runtime/requirements.txt \
    && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' 'jsonschema>=4.23,<5' opentelemetry-sdk \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

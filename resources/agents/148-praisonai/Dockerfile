FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ripgrep     && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent
COPY agent/src/ ./agent/src/
RUN pip install --no-cache-dir ./agent/src/praisonai-agents ./agent/src/praisonai-code     ./agent/src/praisonai-bot ./agent/src/praisonai-train ./agent/src/praisonai-browser     ./agent/src/praisonai-mcp ./agent/src/praisonai-sandbox ./agent/src/praisonai-deploy     './agent/src/praisonai[acp]' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'     && useradd --create-home --uid 10001 agent     && mkdir /workspace && chown agent:agent /workspace
FROM dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent && chown -R agent:agent /home/agent
USER agent

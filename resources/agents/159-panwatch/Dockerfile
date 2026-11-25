FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent DATA_DIR=/home/agent/panwatch PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update && apt-get install -y --no-install-recommends git fonts-noto-cjk libpangoft2-1.0-0 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent/agent
COPY agent/requirements-runtime.txt ./
COPY agent/packages/ ./packages/
RUN pip install --no-cache-dir -r requirements-runtime.txt \
    && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 agent
COPY agent/src/ ./src/
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent /workspace && chown agent:agent /home/agent /workspace
USER agent

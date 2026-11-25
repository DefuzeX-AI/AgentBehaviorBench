FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libffi-dev libssl-dev zip unzip procps \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
USER agent

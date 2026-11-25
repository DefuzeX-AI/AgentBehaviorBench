FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir '.[web]' \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

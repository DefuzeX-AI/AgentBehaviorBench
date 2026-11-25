FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential findutils \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+abb.1775f8b pip install --no-cache-dir '.[all]' \
    'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

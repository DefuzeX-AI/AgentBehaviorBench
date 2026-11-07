# Outer ABB image for DeerFlow's embedded Python client.
# Build context is the outer Agent unit; the upstream checkout is copied from agent/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PATH=/opt/agent/agent/backend/.venv/bin:$PATH \
    HOME=/opt/agent/home \
    DEER_FLOW_PROJECT_ROOT=/opt/agent/agent \
    DEER_FLOW_HOME=/opt/agent/home/.deer-flow \
    DEER_FLOW_CONFIG_PATH=/opt/agent/home/config.yaml

RUN python -m pip install --no-cache-dir uv

COPY agent/ /opt/agent/agent/

WORKDIR /opt/agent/agent/backend
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m ensurepip --upgrade \
    && .venv/bin/python -m pip install --no-cache-dir duckdb==1.5.2 openpyxl==3.1.5 requests \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /opt/agent/home/.deer-flow /opt/agent/workspace \
    && chown -R agent:agent /opt/agent/home /opt/agent/workspace

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

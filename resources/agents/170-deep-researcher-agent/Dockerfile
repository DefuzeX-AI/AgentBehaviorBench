# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir uv==0.12.13
ENV UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/source
# Preserve the relative root and source-package paths used by mcp/uv.lock.
COPY agent/ ./
RUN --mount=type=cache,id=abb-deep-researcher-uv,target=/root/.cache/uv,sharing=locked \
    uv sync --project /opt/source/mcp --frozen --no-dev --no-default-groups --no-editable --python /usr/local/bin/python \
    && /opt/venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python /opt/venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'

FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace /opt/agent/bootstrap \
    && chown -R agent:agent /workspace
COPY --from=dependencies /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/agent \
    XDG_CACHE_HOME=/home/agent/.cache \
    DEEP_RESEARCHER_MCP_CONFIG=/opt/agent/bootstrap/workflow.yml \
    DEEP_RESEARCHER_CHECKPOINT_DB=/workspace/checkpoints.db
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY agent/configs/config_mcp.yml ./bootstrap/upstream-workflow.yml
COPY bootstrap/ ./bootstrap/
RUN python bootstrap/configure.py
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
WORKDIR /workspace

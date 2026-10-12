# Outer ABB image for ai-find-customer (AI Hunter).
# The upstream backend is loose Python source (FastAPI + LangGraph) whose
# pyproject.toml has no build-system or dependencies, so its requirements.txt
# is installed directly and the backend tree is exposed on PYTHONPATH.
# Launch is the BBA worker declared in agent.toml, not the upstream uvicorn
# server, headless worker or React frontend (not needed by the in-process
# LangGraph binding).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/backend

# litellm fetches its model cost map from raw.githubusercontent.com on import
# and falls back to the bundled copy when that fails; that host is not routed,
# so use the bundled copy directly.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True

WORKDIR /opt/agent
COPY agent/backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Upstream config/settings.py resolves writable paths with
# _resolve_dir()/​_resolve_file(), which call mkdir(parents=True) at import
# time under the backend root (data/hunts, uploads, checkpoints and the
# .env location). Those calls run when the LangGraph nodes import
# config.settings, so the backend tree must be writable by the runtime user;
# otherwise every invocation fails with PermissionError on
# /opt/agent/agent/backend/data. The BBA worker runs as this user.
RUN chown -R agent:agent /opt/agent

USER agent

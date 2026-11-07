# Outer ABB image for the Article Explainer LangGraph unit.
# Build context is the outer Agent unit; the untouched upstream checkout is in
# agent/. Launch comes from agent.toml ("python -m
# agentbench.runtime.agentcontainer.worker" from /opt/agent). The upstream
# Streamlit UI and its docker-compose/Ollama stack are not deployed, so no
# frontend stage or web server is built here.

# agent/uv.lock declares requires-python = ">=3.13" with cp313 wheels; build on
# Python 3.13 so the frozen lock resolves. The upstream Dockerfile's
# python3.12 base and Streamlit CMD are not authoritative.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    PATH=/opt/agent/agent/.venv/bin:$PATH

# uv drives the frozen dependency sync. The venv gets pip via ensurepip below
# so the appended SDK overlay can run `python -m pip` against this interpreter.
RUN python -m pip install --no-cache-dir uv==0.12.13

WORKDIR /opt/agent/agent
COPY agent/ ./

# Install exactly the locked dependencies (no dev group; the project itself is
# not installed because pyproject.toml declares no build-system, so uv treats
# it as virtual and the source import root is exposed via PYTHONPATH instead,
# making `from explainer.graph import app` work for the saved binding).
# opentelemetry-sdk covers worker tracing; useradd exists in this Debian base.
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk==1.44.0' \
    && useradd --create-home --uid 10001 agent

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

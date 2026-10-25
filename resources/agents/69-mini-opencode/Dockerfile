FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PATH=/opt/agent/agent/.venv/bin:$PATH \
    MINI_OPENCODE_CONFIG=/opt/agent/agent/abb-config.yaml \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN python -m pip install --no-cache-dir uv==0.13.5 \
    && useradd --create-home --uid 10001 agent

WORKDIR /opt/agent/agent
COPY agent/ ./
# Install the source's exact dependency lock rather than unbounded current APIs.
RUN uv sync --frozen --no-dev \
    && .venv/bin/python -m ensurepip --upgrade
COPY install/abb-runtime-requirements.txt /opt/abb-agent-runtime/requirements.txt
RUN .venv/bin/python -m pip install --no-cache-dir \
    -r /opt/abb-agent-runtime/requirements.txt

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY install/abb-config.yaml ./agent/abb-config.yaml
COPY agent.toml ./agent.toml

RUN mkdir -p /workspace/mini-opencode \
    && chown agent:agent /workspace/mini-opencode
USER agent

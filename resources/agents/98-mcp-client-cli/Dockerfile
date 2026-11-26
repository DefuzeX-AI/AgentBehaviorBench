FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/src \
    PATH=/opt/agent/agent/.venv/bin:$PATH \
    HOME=/home/agent
RUN python -m pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev \
    && .venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/.llm \
    && chown -R agent:agent /home/agent

FROM dependencies
WORKDIR /opt/agent
COPY bootstrap/ ./bootstrap/
RUN python bootstrap/configure.py
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

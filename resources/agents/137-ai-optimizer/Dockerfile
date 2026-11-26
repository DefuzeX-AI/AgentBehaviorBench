FROM python:3.14-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --extra server --extra otel --no-dev \
    && uv pip install --python .venv/bin/python 'jsonschema>=4.23,<5' \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown agent:agent /workspace /home/agent
FROM dependencies
ENV HOME=/home/agent PATH=/opt/agent/agent/.venv/bin:$PATH PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

# Upstream uv.lock requires Python >=3.13; preserve that exact dependency lock.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    PATH=/opt/agent/agent/.venv/bin:$PATH
RUN python -m pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev --no-install-project \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk==1.44.0' \
    && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

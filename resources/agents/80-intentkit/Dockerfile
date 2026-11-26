FROM python:3.13-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
RUN apt-get update && apt-get install -y --no-install-recommends postgresql redis-server git build-essential libpq-dev libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2 fonts-liberation fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/pyproject.toml agent/uv.lock ./
COPY agent/intentkit/ ./intentkit/
COPY agent/public_agents/ ./public_agents/
RUN uv sync --frozen --no-dev --group app \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && .venv/bin/python -m ensurepip --upgrade \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/agent/agent/.venv/bin:$PATH
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent && chown agent:agent /home/agent
USER agent

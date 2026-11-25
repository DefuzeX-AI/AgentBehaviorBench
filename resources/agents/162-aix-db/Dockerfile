FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends postgresql redis-server git build-essential libreoffice poppler-utils \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.24 \
    && useradd --create-home --uid 10001 agent
COPY --from=pgvector/pgvector:pg15-bookworm /usr/lib/postgresql/15/lib/vector.so /usr/lib/postgresql/15/lib/vector.so
COPY --from=pgvector/pgvector:pg15-bookworm /usr/share/postgresql/15/extension/vector* /usr/share/postgresql/15/extension/
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && .venv/bin/python -m ensurepip --upgrade \
    && mkdir -p agent/common/agent_workspace && chown agent:agent agent/common/agent_workspace
ENV PATH=/opt/agent/agent/.venv/bin:$PATH PYTHONPATH=/opt/abb-runtime:/opt/agent/agent HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
USER agent

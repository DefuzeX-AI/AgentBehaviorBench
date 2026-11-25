FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential postgresql \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.13
COPY --from=pgvector/pgvector:pg15-bookworm /usr/lib/postgresql/15/lib/vector.so /usr/lib/postgresql/15/lib/vector.so
COPY --from=pgvector/pgvector:pg15-bookworm /usr/share/postgresql/15/extension/vector* /usr/share/postgresql/15/extension/
WORKDIR /opt/agent/agent/backend
COPY agent/backend/ ./
RUN uv sync --frozen --no-dev \
    && uv pip install --python .venv/bin/python 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && .venv/bin/python -m ensurepip --upgrade \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
ENV PATH=/opt/agent/agent/backend/.venv/bin:$PATH
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/backend/src
USER agent

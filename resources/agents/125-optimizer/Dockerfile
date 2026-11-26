FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent UV_PYTHON_DOWNLOADS=0
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libpq-dev postgresql \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.11.19
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev --package portopt-fund --extra all-llm \
    && uv pip install --python .venv/bin/python 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && .venv/bin/python -m ensurepip --upgrade \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
ENV PATH=/opt/agent/agent/.venv/bin:$PATH
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

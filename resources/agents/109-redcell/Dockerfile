FROM chrislusf/seaweedfs@sha256:bb05d66d2963b1cc48073190781c3dd29e2c4c88a2ae2986bf58e38c86d89c6e AS storage
FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GOMAXPROCS=2 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-15 redis-server git \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
COPY --from=storage /usr/bin/weed /usr/local/bin/weed
WORKDIR /opt/agent/agent
COPY agent/ ./
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --group live --python /usr/local/bin/python \
    && uv pip install --python .venv/bin/python 'agent-client-protocol>=0.7,<1' \
        'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV PATH=/opt/agent/agent/.venv/bin:$PATH
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/apps/api:/opt/agent/agent/packages/core
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

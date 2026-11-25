FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock \
    && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' opentelemetry-sdk jsonschema \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown -R agent:agent /workspace /opt/agent/agent
USER agent

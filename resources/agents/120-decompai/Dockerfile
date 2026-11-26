FROM docker@sha256:851f91d241214e7c6db86513b270d58776379aacc5eb9c4a87e5b47115e3065c AS client
FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 GRADIO_ANALYTICS_ENABLED=False
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
COPY --from=client /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir -r requirements.txt 'agent-client-protocol>=0.7,<1' \
    'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
VOLUME ["/workspace"]
USER agent

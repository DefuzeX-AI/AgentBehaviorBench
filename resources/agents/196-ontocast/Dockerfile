FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir './agent[openai,anthropic,google,ollama,documents]' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/.cache/ontocast /workspace \
    && chown -R agent:agent /home/agent /workspace

FROM dependencies AS embedding_dependencies
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch==2.9.1' \
    && python -m pip install --no-cache-dir 'sentence-transformers==5.1.1'
COPY bootstrap/ /opt/agent/bootstrap/
RUN python bootstrap/cache_embedding.py
ENV AGG_EMBEDDING_MODEL=/opt/models/paraphrase-multilingual-MiniLM-L12-v2 \
    CHUNK_EMBEDDING_MODEL=/opt/models/paraphrase-multilingual-MiniLM-L12-v2 \
    EMBEDDING_MODEL_NAME=/opt/models/paraphrase-multilingual-MiniLM-L12-v2

FROM embedding_dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

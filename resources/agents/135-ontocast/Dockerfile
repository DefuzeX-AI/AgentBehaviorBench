FROM conceptkernel/jena-fuseki:6.0@sha256:04c1bd90627c058d0789f32216b6a484b63738661d8f41ea476955ed8d99e6fe AS fuseki
FROM eclipse-temurin:21-jre-jammy@sha256:affcab5356e1270ac35d2361ee83135af2f03e8d580eca78a6d5d6fdbf048db0 AS java
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    HF_HOME=/opt/agent/tokenizer-cache \
    ONTOCAST_EMBEDDING_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
    ONTOCAST_CACHE_DIR=/home/agent/workspace/cache
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/home/agent/.cache/pip python -m pip install uv==0.8.2
WORKDIR /opt/agent/agent
COPY agent/pyproject.toml agent/uv.lock ./
RUN uv export --frozen --no-dev --extra openai --extra documents --no-emit-project \
    --format requirements-txt --output-file /tmp/ontocast-requirements.txt
RUN --mount=type=cache,target=/home/agent/.cache/uv \
    uv pip install --system --require-hashes -r /tmp/ontocast-requirements.txt
COPY agent/ ./
RUN --mount=type=cache,target=/home/agent/.cache/uv uv pip install --system --no-deps .
RUN python -c "import os; from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2', revision=os.environ['ONTOCAST_EMBEDDING_REVISION'])"
RUN --mount=type=cache,target=/home/agent/.cache/uv uv pip install --system \
    --index-url https://download.pytorch.org/whl/cpu 'torch==2.14.1+cpu'
RUN --mount=type=cache,target=/home/agent/.cache/uv uv pip install --system 'sentence-transformers==6.2.0' \
    && python -m pip check
# Native supported checkpoint configuration: one real CPU encoder for all users.
ENV AGG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    CHUNK_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
    EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
    TOKENIZERS_PARALLELISM=false MALLOC_ARENA_MAX=2
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision=os.environ['ONTOCAST_EMBEDDING_REVISION'], device='cpu')"
# Native consumers use the repository name; resolve it to the pinned cached snapshot offline.
RUN python -c "import os; from pathlib import Path; p=Path(os.environ['HF_HOME'])/'hub/models--sentence-transformers--all-MiniLM-L6-v2/refs/main'; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(os.environ['ONTOCAST_EMBEDDING_REVISION'])"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# ABB's SDK/trace worker dependencies are separate from native Agent dependencies.
RUN --mount=type=cache,target=/home/agent/.cache/pip python -m pip install \
    'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'
COPY --from=java /opt/java/openjdk/ /opt/java/openjdk/
COPY --from=fuseki /fuseki/jena-fuseki-server-6.0.0.jar /opt/fuseki/jena-fuseki-server-6.0.0.jar
COPY --from=fuseki /fuseki/log4j2.properties /opt/fuseki/log4j2.properties
ENV NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
RUN useradd --create-home --user-group --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown agent:agent /home/agent /home/agent/workspace /home/agent/.cache
USER agent

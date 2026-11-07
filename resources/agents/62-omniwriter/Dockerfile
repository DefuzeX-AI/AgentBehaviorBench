# OmniWriter outer ABB image. Build context is the outer Agent unit; the imported
# upstream checkout lives under agent/. Launch is configured in agent.toml
# (`python -m agentbench.runtime.agentcontainer.worker` from /opt/agent), so this
# image declares no ENTRYPOINT/CMD and starts no UI or web server.
#
# Install strategy: uv-locked application. pyproject.toml and uv.lock both
# declare requires-python >=3.12 (the lock carries explicit <3.13 resolution
# markers), so the base interpreter is Python 3.12, the lock's floor. The
# pyproject.toml defines no [build-system], so uv treats the project as virtual:
# dependencies are synced frozen from uv.lock and the application itself runs
# from source with its import root (/opt/agent/agent, top-level `src` package)
# exposed via PYTHONPATH.
FROM docker.elastic.co/elasticsearch/elasticsearch:9.3.0 AS elasticsearch

# OmniWriter creates its full-text index with the `icu_analyzer` declared in
# src/pipeline/tools/rag_tool.py, so the matching official plugin is part of the
# pinned database installation rather than downloaded at Case runtime.
RUN bin/elasticsearch-plugin install --batch analysis-icu

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    ES_JAVA_HOME=/opt/elasticsearch/jdk \
    ES_JAVA_OPTS="-Xms512m -Xmx512m" \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache \
    PATH=/opt/agent/agent/.venv/bin:$PATH

# uv release compatible with the supplied lock format (version = 1, revision = 3).
RUN python -m pip install --no-cache-dir uv==0.12.13

WORKDIR /opt/agent/agent
COPY agent/ ./
COPY --from=elasticsearch /usr/share/elasticsearch /opt/elasticsearch

# Frozen sync installs exactly the locked dependency set (langgraph,
# langchain-openai, chromadb, elasticsearch, deepagents, langfuse, tavily and
# the transitive imports of the DeepAgents branch) without installing the
# project itself. ensurepip bootstraps `python -m pip` inside the venv for the
# appended SDK overlay; opentelemetry-sdk covers the BBA worker's observation
# dependency in the same interpreter. The venv stays on PATH for the worker
# launch, the binding and every later pip invocation.
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' \
    && mkdir -p /opt/tiktoken-cache \
    && .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')" \
    && chmod -R a+rX /opt/tiktoken-cache \
    && useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /opt/elasticsearch

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml

# Non-root runtime user created above (Debian slim provides useradd) with a real
# owned HOME. Model endpoints and credentials (LLM_BASE_URL, LLM_BASE_API_KEY,
# EMBEDDING_*, TAVILY_API_KEY, ES_*) are injected by the runtime environment and
# are never baked into the image; this deployment excludes image generation, so
# no IMAGE_* configuration exists here. Writable runtime state (LOG_DIR,
# CHROMA_STORAGE_PATH, per-user data directories) is provisioned by the
# binding's private workspace at run time. The same binding starts the pinned
# Elasticsearch service on loopback with security disabled; it is reachable only
# inside the Case container and stores its index under that private workspace.
USER agent

# ABB image for lfnovo/open-notebook (chat graph, in-process LangGraph adapter).
# SurrealDB runs inside the Agent container, the same way upstream's own `single`
# image target does (Dockerfile stage "single" + supervisord.surrealdb.conf).
FROM surrealdb/surrealdb:v2.6.5 AS surreal-binary

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache \
    PROMPTS_PATH=/opt/agent/agent/prompts
WORKDIR /opt/agent
COPY --from=surreal-binary /surreal /usr/local/bin/surreal
COPY agent/ ./agent/
# Upstream's uv.lock (consistent with pyproject.toml), exported and installed into the
# interpreter ABB's worker runs. --no-deps: the export is the fully resolved lock, and it
# honours upstream's [tool.uv] pillow override that a re-resolve would reject. o200k_base is
# pre-cached like upstream's image does.
RUN python -m pip install --no-cache-dir uv \
    && cd agent && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt && cd .. \
    && uv pip install --system --no-cache --no-deps -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && mkdir -p /opt/tiktoken-cache \
    && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')" \
    && chmod -R a+rX /opt/tiktoken-cache \
    && surreal version \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml
USER agent

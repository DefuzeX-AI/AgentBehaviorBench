# ABB image for EvoScientist/EvoScientist (main EvoScientist graph, in-process LangGraph adapter).
# Python 3.11 as upstream's own image (ghcr.io/astral-sh/uv:python3.11-trixie-slim).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's uv.lock exported (no dev group, no channel extras) and installed into the
# interpreter ABB's worker runs, then the project itself without re-resolving.
RUN python -m pip install --no-cache-dir uv \
    && cd agent && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt && cd .. \
    && uv pip install --system --no-cache --no-deps -r /tmp/requirements.txt \
    && cp -r agent /tmp/evo-src && uv pip install --system --no-cache --no-deps /tmp/evo-src \
    && rm -rf /tmp/evo-src /tmp/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && mkdir -p /opt/tiktoken-cache \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" \
    && chmod -R a+rX /opt/tiktoken-cache \
    && python -c "from EvoScientist.EvoScientist import create_cli_agent; from EvoScientist.config.settings import get_effective_config; import langchain_openai, langchain_quickjs" \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

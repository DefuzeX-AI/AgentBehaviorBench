FROM python:3.12-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

# LLM_BASE_URL selects the OpenAI-compatible endpoint backend/app/llm.py uses;
# it is the route agent.toml declares for interception. The LLM response cache,
# figures and matplotlib config go to writable per-container paths, as the
# upstream Dockerfile does with /app/data.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LLM_BASE_URL=https://api.openai.com/v1 \
    LLM_CACHE_PATH=/tmp/deepresearch/llm_cache.db \
    FIGURES_DIR=/tmp/deepresearch/figures \
    MPLCONFIGDIR=/tmp/matplotlib \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /opt/agent

# Upstream requirements.txt is pinned; installed unchanged.
COPY agent/requirements.txt ./agent/requirements.txt
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 -r agent/requirements.txt "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN python -c "import sys; sys.path.insert(0, '/opt/agent/agent'); import os; os.environ.setdefault('LLM_API_KEY', 'x'); os.environ.setdefault('TAVILY_API_KEY', 'x'); from backend.app.graph.builder import get_research_graph; get_research_graph()" \
    && chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

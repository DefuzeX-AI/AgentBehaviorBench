FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's pinned requirements.txt, plus langgraph-checkpoint-sqlite (pinned in pyproject.toml but
# missing from requirements.txt; chat_agent.py imports langgraph.checkpoint.sqlite).
RUN python -m pip install --no-cache-dir -r agent/requirements.txt 'langgraph-checkpoint-sqlite==3.0.1' \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" || true \
    && chmod -R a+rX /opt/tiktoken-cache || true \
    && cd agent && python -c "import langgraph.checkpoint.sqlite, langgraph.prebuilt; from langchain_community.tools.tavily_search import TavilySearchResults" && cd .. \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

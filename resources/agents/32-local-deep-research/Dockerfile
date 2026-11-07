# ABB image for LearningCircuit/local-deep-research (langgraph-agent strategy, programmatic API).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    HF_HUB_OFFLINE=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
# CPU-only torch first so sentence-transformers does not pull the CUDA wheels, then the
# pinned upstream snapshot itself (pyproject dependencies, pdm-backend build).
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && cp -r agent /tmp/ldr-src && python -m pip install --no-cache-dir /tmp/ldr-src && rm -rf /tmp/ldr-src \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" \
    && chmod -R a+rX /opt/tiktoken-cache \
    && python -c "from local_deep_research.api import quick_summary; from local_deep_research.advanced_search_system.strategies.langgraph_agent_strategy import LangGraphAgentStrategy" \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

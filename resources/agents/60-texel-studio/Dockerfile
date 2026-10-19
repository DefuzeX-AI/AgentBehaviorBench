FROM python:3.11-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /opt/agent

# The binding runs agent.run_agent_stream only. Its imports are Pillow,
# python-dotenv, langchain-core, langgraph and (for gpt-* model names)
# langchain-openai, at the lower bounds upstream requirements.txt declares.
# The FastAPI server, Gemini/Vertex clients, Redis checkpointer, S3 storage and
# PostHog are not used: REDIS_URL, POSTHOG_API_KEY and the S3 variables stay
# unset, which is upstream's documented self-hosted mode.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        "Pillow>=10.0.0,<12" \
        "python-dotenv>=1.0.0,<2" \
        "langchain>=1.0.0,<2" \
        "langchain-core>=1.0.0,<2" \
        "langgraph>=1.0.0,<2" \
        "langchain-openai>=0.2.0,<2" \
        "opentelemetry-sdk>=1.30,<2" \
    && python -c "from langgraph.prebuilt import create_react_agent; from langgraph.checkpoint.memory import MemorySaver; from langchain_openai import ChatOpenAI" \
    && useradd --create-home --uid 10001 agent

COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

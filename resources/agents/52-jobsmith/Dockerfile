FROM python:3.12-slim

# Rebuild bump: DeepSeek structured-output bypass v2.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    LLM_BACKEND=openai \
    COPILOT_DB=:memory:

WORKDIR /opt/agent

# Runtime for the ABB binding path (OpenAI-compatible BYOK + MemorySaver).
# Desktop/webview and optional doc parsers are omitted.
RUN python -m pip install --no-cache-dir \
      "langgraph>=1.2,<1.3" \
      "langgraph-checkpoint-sqlite>=3.1,<3.2" \
      "langchain-openai>=1.3,<1.4" \
      "langchain-core>=1.4,<1.5" \
      "pydantic>=2.13,<3.0" \
      "python-dotenv>=1.0,<2.0" \
      "requests>=2.31,<3.0" \
      "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN mkdir -p /opt/agent/agent/data \
    && chown -R agent:agent /opt/agent

USER agent

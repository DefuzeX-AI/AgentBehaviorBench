FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /opt/agent

# Minimal runtime deps for the ABB binding path. Heavy native stacks
# (ollama daemon, HuggingFace embeddings, Chroma persistence) are not installed;
# the binding substitutes OpenAI-compatible chat + a baked lexical corpus.
RUN python -m pip install --no-cache-dir \
      "langgraph>=0.2,<2" \
      "langchain-core>=0.3,<2" \
      "langchain-openai>=0.2,<2" \
      "langchain-community>=0.3,<1" \
      "langchain-text-splitters>=0.3,<2" \
      "pydantic>=2,<3" \
      "python-dotenv>=1,<2" \
      "tavily-python>=0.5,<1" \
      "httpx>=0.27,<1" \
      "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY corpus/ ./corpus/
COPY agent.toml ./agent.toml

USER agent

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# Minimal runtime for the ABB binding path. CRM / Google / LinkedIn / Serper /
# Chroma stacks are not installed; the binding substitutes in-memory leads,
# fixture research text, and OpenAI-compatible chat.
RUN python -m pip install --no-cache-dir \
      "langgraph>=0.2,<2" \
      "langchain-core>=0.3,<2" \
      "langchain-openai>=0.2,<2" \
      "langchain-community>=0.3,<1" \
      "pydantic>=2,<3" \
      "python-dotenv>=1,<2" \
      "colorama>=0.4,<1" \
      "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Upstream may write local reports/ beside the source tree.
RUN chown -R agent:agent /opt/agent

USER agent

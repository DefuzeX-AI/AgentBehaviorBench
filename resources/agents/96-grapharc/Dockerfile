FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ripgrep \
    procps \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:$PYTHONPATH \
    HOME=/home/agent

WORKDIR /opt/agent

COPY agent/ ./agent/

RUN python -m pip install --no-cache-dir \
    'langgraph>=0.4' \
    'langgraph-checkpoint-sqlite>=2.0' \
    'langchain-core>=0.3' \
    'langchain-openai>=0.2' \
    'pydantic>=2.7' \
    'opentelemetry-sdk>=1.30,<2' \
    'jsonschema>=4.23,<5' \
    'python-dotenv>=1,<2' \
    && python -m pip install --no-cache-dir -e ./agent --no-deps \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml

USER agent

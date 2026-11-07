FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ripgrep \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent

# Install dependencies
COPY agent/requirements.txt ./agent-requirements.txt
RUN pip install --no-cache-dir -r agent-requirements.txt \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' 'filelock>=3.32.7,<4'

# Setup non-root execution user and workspace
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

COPY agent/ ./agent/
RUN mkdir -p /opt/agent/agent/data/uploads \
             /opt/agent/agent/data/outputs \
             /opt/agent/agent/data/rag_storage \
             /opt/agent/agent/data/history \
             /opt/agent/agent/data/skill \
             /opt/agent/agent/data/sessions \
    && chown -R agent:agent /opt/agent /home/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bindings/ ./bindings/

ENV PYTHONPATH=/opt/agent:/opt/agent/agent:/opt/abb-runtime \
    PYTHONUNBUFFERED=1 \
    HOME=/home/agent \
    DEEPAGENTFORCE_ROOT=/opt/agent/agent

WORKDIR /opt/agent
USER agent

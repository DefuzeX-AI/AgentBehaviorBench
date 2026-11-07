FROM python:3.11-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

RUN sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g; s|security.debian.org|mirrors.cloud.tencent.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ripgrep \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent

# Install dependencies
COPY agent/requirements.txt ./agent-requirements.txt
RUN pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" --timeout 120 --retries 5 -r agent-requirements.txt \
    && pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" --timeout 120 --retries 5 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'

# Setup non-root execution user and workspace
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

COPY --chown=agent:agent agent/ ./agent/
COPY --chown=agent:agent .abb-runtime/ /opt/abb-runtime/
COPY --chown=agent:agent agent.toml ./
COPY --chown=agent:agent network/ ./network/
COPY --chown=agent:agent bindings/ ./bindings/

RUN chown -R agent:agent /home/agent /opt/agent

ENV PYTHONPATH=/opt/agent:/opt/agent/agent:/opt/abb-runtime \
    PYTHONUNBUFFERED=1 \
    HOME=/home/agent

WORKDIR /opt/agent
USER agent

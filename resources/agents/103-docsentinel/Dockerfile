FROM python:3.11-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent:/opt/agent/bindings
ENV HOME=/home/agent
ENV LLM_PROVIDER=deepseek
ENV DEEPSEEK_BASE_URL=https://api.deepseek.com
ENV DEEPSEEK_MODEL=deepseek-chat
ENV LLM_BASE_URL_ALLOWLIST=api.deepseek.com,127.0.0.1,https://api.deepseek.com

WORKDIR /opt/agent

COPY requirements-abb.txt ./
RUN python -m pip install --no-cache-dir \
        --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        -r requirements-abb.txt \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent /home/agent

USER agent

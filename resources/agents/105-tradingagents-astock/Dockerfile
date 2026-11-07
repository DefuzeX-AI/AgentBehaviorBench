# Outer ABB image for TradingAgents-astock. Build context is the outer unit.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

WORKDIR /opt/agent

COPY agent/ ./agent/
# Package metadata pulls langgraph, mootdx (A-share TCP), langchain-*, etc.
RUN python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

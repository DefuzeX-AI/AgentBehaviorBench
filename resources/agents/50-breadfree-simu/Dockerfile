FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    HOME=/tmp

WORKDIR /opt/agent

COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir \
        'langchain-core>=1.2.5,<2' \
        'langgraph>=1.0.5,<2' \
        'openai>=2.14.0,<3' \
        'pandas>=2.3.3,<4' \
        'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /opt/agent/agent/logs \
    && chown -R agent:agent /opt/agent /tmp

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

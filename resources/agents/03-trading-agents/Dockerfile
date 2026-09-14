FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2'  \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

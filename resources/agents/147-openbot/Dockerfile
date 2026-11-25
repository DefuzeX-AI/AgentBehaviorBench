FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/agent-langgraph-agui/requirements.txt /tmp/native-requirements.txt
RUN pip install --no-cache-dir -r /tmp/native-requirements.txt 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'     && useradd --create-home --uid 10001 agent
COPY agent/agent-langgraph-agui/ ./agent/agent-langgraph-agui/
COPY agent/shared/ ./agent/shared/
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/agent-langgraph-agui
FROM dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

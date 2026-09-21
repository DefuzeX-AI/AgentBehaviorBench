# ABB backend image for company-research-agent with langgraph in_process adapter
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# Install Python dependencies from requirements.txt
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent

# Copy BBA runtime overlay
COPY .abb-runtime/ /opt/abb-runtime/

# Copy all agent source and bindings
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

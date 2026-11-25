FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git libmagic1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir . \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

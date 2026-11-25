FROM pgvector/pgvector:pg15-bookworm AS vector
FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-15 build-essential pkg-config dbus \
    libdbus-1-dev libglib2.0-dev portaudio19-dev libasound2-dev libgpiod-dev \
    espeak-ng libespeak1 alsa-utils git libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=vector /usr/lib/postgresql/15/lib/vector.so /usr/lib/postgresql/15/lib/vector.so
COPY --from=vector /usr/share/postgresql/15/extension/vector* /usr/share/postgresql/15/extension/
WORKDIR /opt/agent/agent
COPY agent/src/requirements.txt ./src/requirements.txt
RUN pip install --no-cache-dir -r src/requirements.txt \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace
COPY agent/src/ ./src/
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
RUN chown agent:agent /home/agent
USER agent

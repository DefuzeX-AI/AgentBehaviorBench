# Build the pinned native binary first using Dockerfile.builder.
FROM abb-zed-builder:2f808b3-settings-fix AS builder

FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git ripgrep curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
ENV PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'
WORKDIR /opt/agent
COPY --from=builder /eval-cli /usr/local/bin/zed-eval-cli
COPY agent.toml ./agent.toml
COPY bootstrap/ ./bootstrap/
COPY .abb-runtime/ /opt/abb-runtime/
USER agent

FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright FASTEMBED_CACHE_PATH=/opt/fastembed
RUN apt-get update && apt-get install -y --no-install-recommends git gcc g++ libpq-dev curl ffmpeg libmagic1 \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r backend/requirements.txt agent-client-protocol opentelemetry-sdk jsonschema \
    && python -m playwright install --with-deps chromium \
    && python -c 'from fastembed import TextEmbedding; TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir="/opt/fastembed")' \
    && chown -R agent:agent /opt/agent/agent /opt/fastembed
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir /workspace && chown agent:agent /workspace
USER agent

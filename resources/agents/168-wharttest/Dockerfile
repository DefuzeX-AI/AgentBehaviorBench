FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential redis-server postgresql-15 libmagic1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent/agent/WHartTest_Django
COPY agent/WHartTest_Django/ ./
COPY agent/WHartTest_Skills/ /opt/agent/agent/WHartTest_Skills/
RUN pip install --no-cache-dir -r requirements.txt -r skill_runner/requirements.txt \
    'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && mkdir -p logs media && chown agent:agent logs media
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/WHartTest_Django
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN chown -R agent:agent /opt/agent/agent/WHartTest_Django
USER agent

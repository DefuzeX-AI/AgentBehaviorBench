FROM python:3.11-slim-bookworm AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 agent
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/agent/agent
COPY agent/ ./
COPY constraints.txt /opt/jar3d-constraints.txt
ENV PIP_CONSTRAINT=/opt/jar3d-constraints.txt
RUN pip install --no-cache-dir -r requirements.txt 'python-socketio[asyncio_client]' \
    'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && playwright install --with-deps chromium
RUN chown -R agent:agent /opt/agent/agent && mkdir -p /home/agent/.cache \
    && if [ -d /root/.cache/ms-playwright ]; then cp -a /root/.cache/ms-playwright /home/agent/.cache/; fi \
    && chown -R agent:agent /home/agent/.cache
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

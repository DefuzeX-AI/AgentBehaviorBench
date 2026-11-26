FROM node:22-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git \
    xvfb xauth libnss3 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libasound2 libdrm2 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir agent-client-protocol 'jsonschema>=4.23,<5' opentelemetry-sdk
WORKDIR /opt/agent/agent
COPY agent/ ./
WORKDIR /opt/agent/agent/electron
RUN npm ci && npm run build \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown agent:agent /workspace /home/agent
FROM dependencies
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
USER agent

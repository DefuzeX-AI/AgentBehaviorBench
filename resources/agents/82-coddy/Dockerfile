# Coddy's official release is a static binary; its native ACP server is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash git ripgrep curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/coddy.tar.gz "$url" \
    && echo "$sha  /tmp/coddy.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/coddy && tar -xzf /tmp/coddy.tar.gz -C /opt/coddy coddy \
    && rm /tmp/coddy.tar.gz && chmod 0755 /opt/coddy/coddy && /opt/coddy/coddy -v \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
USER agent

# Install the pinned, sha256-verified pi-go release binary (`pi`); its ACP server
# (`pi acp-server`) is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/pi-go/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/pi-go.tar.gz "$url" \
    && echo "$sha  /tmp/pi-go.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/pi-go/bin && tar -xzf /tmp/pi-go.tar.gz -C /opt/pi-go/bin pi \
    && rm /tmp/pi-go.tar.gz && chmod 0755 /opt/pi-go/bin/pi && /opt/pi-go/bin/pi --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

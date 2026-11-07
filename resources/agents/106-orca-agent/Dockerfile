# Install the pinned, sha256-verified Orca release binary; its ACP mode
# (`orca --mode=acp`) is built in. The binary needs glibc >= 2.39 (trixie).
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/orca/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/orca.tar.gz "$url" \
    && echo "$sha  /tmp/orca.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/orca/bin && tar -xzf /tmp/orca.tar.gz -C /opt/orca/bin orca \
    && rm /tmp/orca.tar.gz && chmod 0755 /opt/orca/bin/orca && /opt/orca/bin/orca --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Install the pinned, sha256-verified Zeph release binary (static musl, built with
# the ACP feature: `zeph --acp`) and the default.toml of the same commit, which the
# launcher adapts per Case (Zeph refuses a partial config).
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/zeph/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/zeph.tar.gz "$url" \
    && echo "$sha  /tmp/zeph.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/zeph/bin && tar -xzf /tmp/zeph.tar.gz -C /opt/zeph/bin zeph \
    && rm /tmp/zeph.tar.gz && chmod 0755 /opt/zeph/bin/zeph && /opt/zeph/bin/zeph --version \
    && cfg_url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['default_config_url'])") \
    && cfg_sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['default_config_sha256'])") \
    && mkdir -p /opt/zeph/share && curl -fsSL --retry 3 -o /opt/zeph/share/default.toml "$cfg_url" \
    && echo "$cfg_sha  /opt/zeph/share/default.toml" | sha256sum -c - \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

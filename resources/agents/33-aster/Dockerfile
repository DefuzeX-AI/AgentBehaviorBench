# Install the pinned, sha256-verified Aster release binary (static musl); its ACP
# server (`aster acp`) is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/aster/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/aster.tar.gz "$url" \
    && echo "$sha  /tmp/aster.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/aster/bin && tar -xzf /tmp/aster.tar.gz -C /opt/aster/bin --strip-components=1 aster-0.7.1-x86_64-unknown-linux-musl/aster \
    && rm /tmp/aster.tar.gz && chmod 0755 /opt/aster/bin/aster && /opt/aster/bin/aster --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

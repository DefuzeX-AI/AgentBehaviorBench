# Install the pinned, sha256-verified Waveloom release binary; its ACP server
# (`waveloom acp`) is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/waveloom/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/waveloom.tar.gz "$url" \
    && echo "$sha  /tmp/waveloom.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/waveloom/bin && tar -xzf /tmp/waveloom.tar.gz -C /opt/waveloom/bin waveloom \
    && rm /tmp/waveloom.tar.gz && chmod 0755 /opt/waveloom/bin/waveloom && /opt/waveloom/bin/waveloom --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

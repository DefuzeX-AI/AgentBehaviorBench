# Install the pinned, sha256-verified Reasonix release; its ACP server (`reasonix acp`) is built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/reasonix/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/reasonix.tar.gz "$url" \
    && echo "$sha  /tmp/reasonix.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/reasonix/bin \
    && tar -xzf /tmp/reasonix.tar.gz -C /opt/reasonix/bin reasonix \
    && rm /tmp/reasonix.tar.gz && chmod 0755 /opt/reasonix/bin/reasonix \
    && /opt/reasonix/bin/reasonix --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

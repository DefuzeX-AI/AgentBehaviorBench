# Install the pinned, sha256-verified Open Interpreter release package; its ACP server (`interpreter acp`) is built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/open-interpreter/bin:/opt/open-interpreter/codex-path:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/oi.tar.gz "$url" \
    && echo "$sha  /tmp/oi.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/open-interpreter && tar -xzf /tmp/oi.tar.gz -C /opt/open-interpreter \
    && rm /tmp/oi.tar.gz && rm -f /opt/open-interpreter/bin/i \
    && /opt/open-interpreter/bin/interpreter --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent \
    && chmod 0777 /home/agent/workspace \
    && mkdir -m 1777 /var/lib/abb-open-interpreter
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

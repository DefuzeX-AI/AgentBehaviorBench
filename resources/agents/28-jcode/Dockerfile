# Install the pinned, sha256-verified jcode release; its ACP adapter (`jcode acp`) is built in.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/jcode/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/jcode.tar.gz "$url" \
    && echo "$sha  /tmp/jcode.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/jcode/bin \
    && tar -xzf /tmp/jcode.tar.gz -C /opt/jcode/bin jcode-linux-x86_64 jcode-linux-x86_64.bin \
    && rm /tmp/jcode.tar.gz && chmod 0755 /opt/jcode/bin/jcode-linux-x86_64 /opt/jcode/bin/jcode-linux-x86_64.bin \
    && ln -s jcode-linux-x86_64 /opt/jcode/bin/jcode && /opt/jcode/bin/jcode --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

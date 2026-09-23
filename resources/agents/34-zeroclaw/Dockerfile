# Install the pinned, sha256-verified ZeroClaw release binary; its ACP server (`zeroclaw acp`) is built in.
FROM python:3.12-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python -m venv /opt/venv
ENV PATH=/opt/zeroclaw/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN field() { python -c "import json,sys;print(json.load(open('agent/distribution.json'))[sys.argv[1]])" "$1"; } \
    && curl -fsSL --retry 3 -o /tmp/zeroclaw.tgz "$(field url)" \
    && echo "$(field sha256)  /tmp/zeroclaw.tgz" | sha256sum -c - \
    && mkdir -p /opt/zeroclaw/bin && tar -xzf /tmp/zeroclaw.tgz -C /opt/zeroclaw/bin "$(field archive_member)" \
    && rm /tmp/zeroclaw.tgz && chmod 0755 /opt/zeroclaw/bin/zeroclaw && /opt/zeroclaw/bin/zeroclaw --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

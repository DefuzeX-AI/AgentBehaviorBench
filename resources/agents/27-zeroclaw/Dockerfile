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

# Headless Chromium for the browser tool. abb-chromium imports the interceptor CA into
# Chromium's NSS store before launch; zz-abb-lean keeps Chromium within the container's
# pid budget (#158).
USER root
RUN apt-get update && apt-get install -y --no-install-recommends chromium libnss3-tools fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY abb-chromium /usr/local/bin/abb-chromium
RUN chmod 755 /usr/local/bin/abb-chromium
COPY zz-abb-lean /etc/chromium.d/zz-abb-lean

# agent-browser CLI (ZeroClaw's agent_browser backend), native linux-x64 binary
USER root
RUN curl -fsSL --retry 3 -o /tmp/agent-browser.tgz https://registry.npmjs.org/agent-browser/-/agent-browser-0.38.1.tgz \
    && echo '89a7df4761ff335e4dd5367e4cf04cecb9ba4e2cc130a0220f798d188414dc6c  /tmp/agent-browser.tgz' | sha256sum -c - \
    && tar -xzf /tmp/agent-browser.tgz -C /tmp package/bin/agent-browser-linux-x64 \
    && install -m 0755 /tmp/package/bin/agent-browser-linux-x64 /usr/local/bin/agent-browser \
    && rm -rf /tmp/agent-browser.tgz /tmp/package && agent-browser --version
USER agent

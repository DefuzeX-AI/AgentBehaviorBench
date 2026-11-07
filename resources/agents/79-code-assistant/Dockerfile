# Install the pinned, sha256-verified code-assistant release binary; its ACP
# mode (`code-assistant acp`) is built in. The binary is the same one as the GUI
# build: it needs glibc >= 2.39 (trixie) and links the xkbcommon/xcb libraries
# even when no window is opened.
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
        libxkbcommon0 libxkbcommon-x11-0 libxcb1 libxau6 libssl3t64 zlib1g \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/code-assistant/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/code-assistant.zip "$url" \
    && echo "$sha  /tmp/code-assistant.zip" | sha256sum -c - \
    && mkdir -p /opt/code-assistant/bin \
    && python3 -c "import zipfile;zipfile.ZipFile('/tmp/code-assistant.zip').extract('code-assistant','/opt/code-assistant/bin')" \
    && rm /tmp/code-assistant.zip && chmod 0755 /opt/code-assistant/bin/code-assistant \
    && /opt/code-assistant/bin/code-assistant --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

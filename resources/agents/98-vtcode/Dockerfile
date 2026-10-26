# Install the pinned, sha256-verified VT Code release binary for the build
# architecture; its ACP server (`vtcode acp`) is built in. No Rust build is needed.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/vtcode/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN arch=$(uname -m) \
    && url=$(python3 -c "import json,sys;print(json.load(open('agent/distribution.json'))['platforms'][sys.argv[1]]['url'])" "$arch") \
    && sha=$(python3 -c "import json,sys;print(json.load(open('agent/distribution.json'))['platforms'][sys.argv[1]]['sha256'])" "$arch") \
    && curl -fsSL --retry 3 -o /tmp/vtcode.tar.gz "$url" \
    && echo "$sha  /tmp/vtcode.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/vtcode/bin && tar -xzf /tmp/vtcode.tar.gz -C /opt/vtcode/bin ./vtcode \
    && rm /tmp/vtcode.tar.gz && chmod 0755 /opt/vtcode/bin/vtcode \
    && USER=agent /opt/vtcode/bin/vtcode --version > /dev/null && rm -rf /root/.config /root/.local /root/.cache \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

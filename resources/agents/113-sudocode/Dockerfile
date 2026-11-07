# Install the pinned, sha256-verified Sudo Code (scode) release binary for the build
# architecture; its ACP server (`scode acp`) is built in. No Rust build is needed.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/scode/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent \
    SCODE_CHECK_UPDATES=0
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN set -eu; \
    arch="$(uname -m)"; \
    field() { python3 -c "import json,sys;print(json.load(open('agent/distribution.json'))['platforms'][sys.argv[1]][sys.argv[2]])" "$arch" "$1"; }; \
    curl -fsSL --retry 3 -o /tmp/scode.tar.gz "$(field url)"; \
    echo "$(field sha256)  /tmp/scode.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/scode/bin; \
    tar -xzf /tmp/scode.tar.gz -C /tmp "$(field archive_member)"; \
    install -m 0755 "/tmp/$(field archive_member)" /opt/scode/bin/scode; \
    rm -rf /tmp/scode.tar.gz /tmp/scode-linux-*; \
    /opt/scode/bin/scode --version; \
    python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'; \
    useradd --create-home --uid 10001 agent; \
    mkdir -p /home/agent/workspace; \
    chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

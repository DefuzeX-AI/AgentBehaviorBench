# Install the pinned, sha256-verified Moltis release binary for the build
# architecture; its ACP server (`moltis acp`) is built in. No Rust build is needed.
# The release links glibc 2.39 and libgomp, so the base is Debian trixie.
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git libgomp1 ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/moltis/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent \
    MOLTIS_SHARE_DIR=/opt/moltis/share/moltis
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN set -eu; \
    arch="$(uname -m)"; \
    field() { python3 -c "import json,sys;print(json.load(open('agent/distribution.json'))['platforms'][sys.argv[1]][sys.argv[2]])" "$arch" "$1"; }; \
    curl -fsSL --retry 3 -o /tmp/moltis.tar.gz "$(field url)"; \
    echo "$(field sha256)  /tmp/moltis.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/moltis/bin /opt/moltis/share; \
    tar -xzf /tmp/moltis.tar.gz -C /tmp moltis share; \
    install -m 0755 /tmp/moltis /opt/moltis/bin/moltis; \
    mv /tmp/share/moltis /opt/moltis/share/moltis; \
    rm -rf /tmp/moltis.tar.gz /tmp/moltis /tmp/share; \
    /opt/moltis/bin/moltis --version; \
    python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'; \
    useradd --create-home --uid 10001 agent; \
    mkdir -p /home/agent/workspace; \
    chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

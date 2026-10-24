# Install the pinned, sha256-verified kimchi release (a self-contained Bun binary plus
# its share/ assets); its ACP server (`kimchi --mode acp`) is built in.
FROM python:3.12-slim-bookworm
# ripgrep and fd are preinstalled so Pi's search tools never download them; git is
# used by the shell tool and kimchi's work-attribution extension.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep fd-find \
    && rm -rf /var/lib/apt/lists/* && ln -s /usr/bin/fdfind /usr/local/bin/fd
ENV PATH=/opt/kimchi/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    field() { python3 -c "import json,sys;print(json.load(open('agent/distribution.json'))['platforms'][sys.argv[1]][sys.argv[2]])" "$arch" "$1"; }; \
    curl -fsSL --retry 3 -o /tmp/kimchi.tar.gz "$(field url)"; \
    echo "$(field sha256)  /tmp/kimchi.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/kimchi; tar -xzf /tmp/kimchi.tar.gz -C /opt/kimchi bin/kimchi share/kimchi; rm /tmp/kimchi.tar.gz; \
    chmod 0755 /opt/kimchi/bin/kimchi; KIMCHI_NO_UPDATE_CHECK=1 /opt/kimchi/bin/kimchi --version; \
    python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'; \
    useradd --create-home --uid 10001 agent; \
    mkdir -p /home/agent/workspace; \
    chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

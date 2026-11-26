# Install the pinned, sha256-verified Stakpak release archive (statically linked
# binary); its ACP server (`stakpak acp`) is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/stakpak/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && mkdir -p /opt/stakpak/bin /tmp/stakpak \
    && curl -fsSL --retry 3 -o /tmp/stakpak/stakpak.tar.gz "$url" \
    && echo "$sha  /tmp/stakpak/stakpak.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/stakpak/stakpak.tar.gz -C /tmp/stakpak \
    && install -m 0755 /tmp/stakpak/stakpak /opt/stakpak/bin/stakpak && rm -rf /tmp/stakpak \
    && /opt/stakpak/bin/stakpak --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

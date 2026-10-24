# Install the pinned, sha256-verified fx release archive (statically linked
# binary); its ACP server (`fx acp`) is built in.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/fx/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && mkdir -p /opt/fx/bin /tmp/fx \
    && curl -fsSL --retry 3 -o /tmp/fx/fx.tar.gz "$url" \
    && echo "$sha  /tmp/fx/fx.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/fx/fx.tar.gz -C /tmp/fx \
    && install -m 0755 /tmp/fx/fx /opt/fx/bin/fx && rm -rf /tmp/fx \
    && /opt/fx/bin/fx --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

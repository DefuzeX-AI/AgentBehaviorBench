# Install the pinned, sha256-verified OpenCrabs release archive; its ACP server
# (`opencrabs acp`) is built in. The binary needs glibc >= 2.43 and libgomp, so
# the unit uses Ubuntu 26.04 with a venv for ABB's Python runtime.
FROM ubuntu:26.04
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git ripgrep libgomp1 python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:/opt/opencrabs/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && mkdir -p /opt/opencrabs/bin /tmp/opencrabs \
    && curl -fsSL --retry 3 -o /tmp/opencrabs/opencrabs.tar.gz "$url" \
    && echo "$sha  /tmp/opencrabs/opencrabs.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/opencrabs/opencrabs.tar.gz -C /tmp/opencrabs \
    && install -m 0755 /tmp/opencrabs/opencrabs /tmp/opencrabs/rtk /opt/opencrabs/bin/ && rm -rf /tmp/opencrabs \
    && /opt/opencrabs/bin/opencrabs --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

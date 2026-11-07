# Install the pinned, sha256-verified Claurst release binary; its ACP server (`claurst acp`) is built in.
# The v0.1.7 Linux binary needs GLIBC 2.39 and libasound, so the base is Debian trixie.
FROM node:24-trixie
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl libasound2t64 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/claurst/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && curl -fsSL --retry 3 -o /tmp/claurst.tar.gz "$url" \
    && echo "$sha  /tmp/claurst.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/claurst/bin && tar -xzf /tmp/claurst.tar.gz -C /opt/claurst/bin claurst \
    && rm /tmp/claurst.tar.gz && chmod 0755 /opt/claurst/bin/claurst && /opt/claurst/bin/claurst --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent \
    && chmod 0755 /home/agent && chmod 0777 /home/agent/workspace
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

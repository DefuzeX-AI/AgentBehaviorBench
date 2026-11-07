# Install the pinned, sha256-verified siGit Code release binary; its ACP server
# (`sigit --acp`) is built in. The v1.7.4 Linux binary needs GLIBC 2.39, so the
# base is Debian trixie (glibc 2.40).
FROM node:24-trixie
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/sigit/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN url=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['url'])") \
    && sha=$(python3 -c "import json;print(json.load(open('agent/distribution.json'))['sha256'])") \
    && mkdir -p /opt/sigit/bin \
    && curl -fsSL --retry 3 -o /opt/sigit/bin/sigit "$url" \
    && echo "$sha  /opt/sigit/bin/sigit" | sha256sum -c - \
    && chmod 0755 /opt/sigit/bin/sigit && /opt/sigit/bin/sigit --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

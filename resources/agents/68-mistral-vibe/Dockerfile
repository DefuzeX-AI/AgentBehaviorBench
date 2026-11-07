# Install the pinned Mistral Vibe release (hash-locked PyPI closure) into its own
# venv; its ACP server (`vibe-acp`) is built in. Vibe requires Python >= 3.12.
FROM python:3.13-bookworm
# ripgrep is preinstalled so Vibe's grep tool uses a local rg binary.
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv && python -m venv /opt/vibe
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN /opt/vibe/bin/python -m pip install --no-cache-dir --require-hashes --no-deps -r agent/requirements.txt \
    && /opt/vibe/bin/vibe-acp --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

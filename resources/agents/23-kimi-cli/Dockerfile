# Install the pinned Kimi Code CLI release (hash-locked PyPI closure) into its own
# venv; its ACP server (`kimi acp`) is built in. Kimi requires Python >= 3.12.
FROM python:3.13-bookworm
# ripgrep is preinstalled because Kimi's Grep tool otherwise downloads rg from
# cdn.kimi.com on first use, which is outside the admitted model route.
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv && python -m venv /opt/kimi
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent \
    KIMI_CLI_NO_AUTO_UPDATE=1 KIMI_DISABLE_TELEMETRY=1
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN /opt/kimi/bin/python -m pip install --no-cache-dir --require-hashes --no-deps -r agent/requirements.txt \
    && /opt/kimi/bin/kimi --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

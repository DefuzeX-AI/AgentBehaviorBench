# Install pinned Mini-Agent source with its uv.lock dependency closure (hash-checked, from
# PyPI) into its own venv; its ACP server is `mini_agent.acp` (`mini-agent-acp`).
FROM python:3.12-bookworm
RUN python -m venv /opt/venv && python -m venv /opt/mini-agent
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# uv exports the lock (whose wheel URLs point at a PyPI mirror) so pip installs the same
# pinned versions and hashes from PyPI. uv stays installed: Mini-Agent's system prompt
# directs Python work through `uv`.
RUN python -m pip install --no-cache-dir 'uv==0.11.15' \
    && uv export --project agent --frozen --no-dev --no-emit-project \
       --format requirements-txt -o /tmp/mini-agent-requirements.txt \
    && /opt/mini-agent/bin/python -m pip install --no-cache-dir --require-hashes --no-deps \
       -r /tmp/mini-agent-requirements.txt \
    && /opt/mini-agent/bin/python -m pip install --no-cache-dir --no-deps ./agent \
    && /opt/mini-agent/bin/python -c 'import mini_agent.acp' \
    && rm /tmp/mini-agent-requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Historical source build: upstream gptme is checked out at the requested commit
# in agent/ and installed from its own uv.lock with the acp extra, into the same
# /opt/agent-venv (gptme-acp) and tiktoken cache layout as the release image.
FROM python:3.12-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir uv==0.12.24
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent \
    && UV_PROJECT_ENVIRONMENT=/opt/agent-venv UV_PYTHON=/usr/local/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
       UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-default-groups --extra acp --no-editable --link-mode=copy \
    && rm -rf /tmp/uv-cache \
    && HOME=/tmp/abb-build-home /opt/agent-venv/bin/python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" \
    && chmod -R a+rX "$TIKTOKEN_CACHE_DIR" \
    && HOME=/tmp/abb-build-home /opt/agent-venv/bin/python -c "import acp, gptme.acp.agent" \
    && test -x /opt/agent-venv/bin/gptme-acp \
    && rm -rf /tmp/abb-build-home \
    && /opt/venv/bin/python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

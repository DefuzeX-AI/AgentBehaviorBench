# Build the selected upstream commit from its own uv.lock with the [acp] extra;
# its ACP server (`gptme-acp`) is an entry point of the root gptme package.
FROM python:3.12-bookworm
# tiktoken downloads BPE files from openaipublic.blob.core.windows.net on first
# use, outside the admitted model route; cache the encodings gptme selects
# (cl100k_base for unknown models, o200k_base for current OpenAI names) at build.
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir uv==0.11.15
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache \
    UV_PROJECT_ENVIRONMENT=/opt/agent-venv UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent \
    && uv sync --frozen --no-dev --no-editable --extra acp --python /usr/local/bin/python3.12 \
    && HOME=/tmp/abb-build-home /opt/agent-venv/bin/python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" \
    && chmod -R a+rX "$TIKTOKEN_CACHE_DIR" \
    && HOME=/tmp/abb-build-home /opt/agent-venv/bin/python -c "import acp, gptme.acp.agent" \
    && test -x /opt/agent-venv/bin/gptme-acp \
    && rm -rf /tmp/abb-build-home \
    && /opt/venv/bin/python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY provenance.json ./provenance.json
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

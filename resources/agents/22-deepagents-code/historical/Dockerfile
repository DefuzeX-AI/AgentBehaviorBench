# Historical source build: the upstream monorepo is checked out at the requested
# commit in agent/; the deepagents-code CLI is libs/code (its uv.lock resolves the
# sibling libs/deepagents and libs/acp from the same checkout). Same layout as the
# release image: /opt/agent-venv/bin/deepagents-code and the certifi link.
FROM python:3.12-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir uv==0.12.24
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent/libs/code \
    && UV_PROJECT_ENVIRONMENT=/opt/agent-venv UV_PYTHON=/usr/local/bin/python3.12 UV_PYTHON_DOWNLOADS=never \
       UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-default-groups --no-editable --link-mode=copy \
    && rm -rf /tmp/uv-cache \
    && test -x /opt/agent-venv/bin/deepagents-code && /opt/agent-venv/bin/python -c "import deepagents_code, deepagents_acp" \
    && cert=$(/opt/agent-venv/bin/python -c 'import certifi; print(certifi.where())') \
    && mv "$cert" "${cert%.pem}.orig.pem" && ln -s /tmp/abb-deepagents-certifi.pem "$cert" \
    && /opt/venv/bin/python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

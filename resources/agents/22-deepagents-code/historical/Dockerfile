# Build the selected upstream commit from its own uv.lock. libs/code pins the
# local libs/deepagents, libs/acp and libs/partners/quickjs packages by path;
# they are installed non-editable into the venv the bootstrap launches.
FROM python:3.12-bookworm
# fetch_url uses a requests Session with trust_env=False (SSRF guard), so it
# verifies TLS only against certifi's bundle and ignores REQUESTS_CA_BUNDLE.
# certifi's cacert.pem is a link to a per-container file that
# bootstrap/launch.py writes from the original bundle plus the runtime CA.
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir uv==0.11.15
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent \
    UV_PROJECT_ENVIRONMENT=/opt/agent-venv UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent/libs/code \
    && uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python3.12 \
    && HOME=/tmp/abb-build-home /opt/agent-venv/bin/python -c "import deepagents, deepagents_acp, deepagents_code" \
    && test -x /opt/agent-venv/bin/deepagents-code && rm -rf /tmp/abb-build-home \
    && cert=$(/opt/agent-venv/bin/python -c 'import certifi; print(certifi.where())') \
    && mv "$cert" "${cert%.pem}.orig.pem" && ln -s /tmp/abb-deepagents-certifi.pem "$cert" \
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

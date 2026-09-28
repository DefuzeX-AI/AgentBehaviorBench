# Install the pinned deepagents-code release (hash-locked pip closure) into its own venv; its ACP server is built in.
FROM python:3.12-bookworm
# fetch_url uses a requests Session with trust_env=False (SSRF guard), so it
# verifies TLS only against certifi's bundle and ignores REQUESTS_CA_BUNDLE.
# certifi's cacert.pem is a link to a per-container file that
# bootstrap/launch.py writes from the original bundle plus the runtime CA.
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv && python3 -m venv /opt/agent-venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN /opt/agent-venv/bin/python -m pip install --no-cache-dir --require-hashes -r agent/requirements.txt \
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

FROM ubuntu:24.04
RUN apt-get -o Acquire::Retries=2 update && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=2 install -y --no-install-recommends python3-venv ca-certificates libssl3t64 && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY bootstrap/install_native.py /tmp/install_native.py
# Docker Desktop may inject a dead http.docker.internal:3128 proxy; clear it for the official release fetch.
RUN HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
    python /tmp/install_native.py /usr/local/bin/openbitfun \
    && rm /tmp/install_native.py && openbitfun --version
RUN python -m pip install --no-cache-dir 'agent-client-protocol==0.12.1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

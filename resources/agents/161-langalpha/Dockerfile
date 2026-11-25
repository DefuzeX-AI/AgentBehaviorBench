FROM python:3.13-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential openssh-server curl chromium \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.24 \
    && useradd --create-home --uid 10001 --shell /bin/bash agent \
    && usermod -p '*' agent && mkdir -p /run/sshd /home/workspace && chown agent:agent /home/workspace
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && .venv/bin/python -m ensurepip --upgrade
ENV PATH=/opt/agent/agent/.venv/bin:$PATH PYTHONPATH=/opt/abb-runtime:/opt/agent/agent:/opt/agent/agent/src HOME=/home/agent
ENV TIKTOKEN_CACHE_DIR=/home/agent/.cache/tiktoken
USER agent
RUN python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base"); tiktoken.get_encoding("o200k_base")'
RUN python -c 'from ptc_agent.core.sandbox.providers._ssh_bootstrap import bootstrap_script; import subprocess; subprocess.run(["bash", "-c", bootstrap_script(lock_wait_s=1800)], check=True)'
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml

FROM python:3.12-slim

ARG ABB_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/src \
    ROW_BOT_AUTO_START_OLLAMA=0 \
    ROW_BOT_TEST_MODE=1 \
    PIP_INDEX_URL=${ABB_PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/agent

RUN apt-get -o Acquire::Retries=2 update \
    && apt-get -o Acquire::Retries=2 install -y --no-install-recommends \
        ca-certificates \
        libglib2.0-0 \
        libgomp1 \
        libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent

# Avoid setuptools ClientBuildPy (frontend payload). Install deps only; import via PYTHONPATH.
COPY install/requirements-abb.txt /tmp/requirements-abb.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-abb.txt \
    && rm /tmp/requirements-abb.txt

COPY agent/ ./agent/
RUN python -c "import row_bot; import row_bot.agent; print('row_bot import ok')"

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
COPY network/ ./network/
COPY source-manifest.json ./source-manifest.json
COPY requirement.md ./requirement.md

RUN chown -R agent:agent /opt/agent

USER agent
WORKDIR /home/agent/workspace

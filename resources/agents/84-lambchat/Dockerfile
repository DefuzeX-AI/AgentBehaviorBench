FROM python:3.12-slim

# Package index override for the dependency layer. Default matches other ABB
# China-region units (tencent mirror); override with --build-arg when needed.
# Prefer Tsinghua mirror (tencent timed out; plain PyPI was too slow for the
# 30-minute ABB Docker build budget on this host).
ARG ABB_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    CHECKPOINT_BACKEND=disabled \
    PIP_INDEX_URL=${ABB_PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/agent

# QuickAgent-only dependency set. Full upstream uv.lock pulls Daytona/E2B,
# Mongo/Postgres checkpoints, webpush, OCR, etc. - out of scope for ABB.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent

COPY requirements-abb.txt /tmp/requirements-abb.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-abb.txt \
    && rm /tmp/requirements-abb.txt

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/src ./agent/src/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
COPY source-manifest.json ./source-manifest.json

RUN chown -R agent:agent /opt/agent

USER agent

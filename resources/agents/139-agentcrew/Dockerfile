FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
ARG ABB_DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG ABB_DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
ARG ABB_PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent UV_PROJECT_ENVIRONMENT=/opt/agentcrew-venv UV_PYTHON_DOWNLOADS=never \
    CHROME_BIN=/usr/bin/chromium AGENTCREW_DISABLE_GUI=true \
    XDG_CACHE_HOME=/home/agent/.cache
RUN sed -i "s|http://deb.debian.org/debian-security|${ABB_DEBIAN_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${ABB_DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=2 update && apt-get -o Acquire::Retries=2 install -y --no-install-recommends \
    build-essential pkg-config git curl ca-certificates ripgrep nodejs npm chromium \
    libglib2.0-0 libgl1 libportaudio2 libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --index-url "${ABB_PIP_INDEX_URL}" uv==0.13.5
WORKDIR /opt/agent
COPY agent/ ./agent/
# Keep native dependencies separate from ABB's worker and SDK overlays.
RUN --mount=type=cache,target=/root/.cache/uv export UV_CACHE_DIR=/root/.cache/uv \
    && cd agent \
    && uv export --quiet --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/agentcrew-locked.txt \
    && uv venv /opt/agentcrew-venv \
    && uv pip install --python /opt/agentcrew-venv/bin/python --index-url "${ABB_PIP_INDEX_URL}" --require-hashes -r /tmp/agentcrew-locked.txt \
    && uv pip install --python /opt/agentcrew-venv/bin/python --index-url "${ABB_PIP_INDEX_URL}" --no-deps . \
    && uv pip check --python /opt/agentcrew-venv/bin/python
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace /home/agent/.cache \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
# Populate native parser and embedding caches as their eventual runtime owner.
RUN /opt/agentcrew-venv/bin/python -c "from tree_sitter_language_pack import download_all; download_all()"
RUN /opt/agentcrew-venv/bin/python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['Cache preparation'])"
USER root
RUN python -m pip install --no-cache-dir --index-url "${ABB_PIP_INDEX_URL}" 'opentelemetry-sdk>=1.30,<2'
USER agent

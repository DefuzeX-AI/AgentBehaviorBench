FROM python:3.12-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /opt/agent

# ripgrep is a hard requirement (ra_aid/dependencies.py); git is used by the
# project/file tools; libmagic backs python-magic.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep git libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies come from upstream's uv.lock (frozen, no dev group); the package
# itself is then installed without re-resolving.
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" uv \
    && cd agent && uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/ra-aid-requirements.txt && cd .. \
    && python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 -r /tmp/ra-aid-requirements.txt "opentelemetry-sdk>=1.30,<2" \
    && python -m pip install --no-cache-dir --no-deps ./agent \
    && python -c "import ra_aid.__main__" \
    && useradd --create-home --uid 10001 agent \
    && git config --system user.name "RA.Aid" \
    && git config --system user.email "ra-aid@localhost"

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

# Upstream requires Python >=3.11,<4 and notes that jieba (its Chinese text
# segmenter for BM25 catalog retrieval) is not compatible with Python 3.12+,
# so the deployment stays on 3.11.
FROM python:3.11-slim

# Package index override for the dependency layer, so a build can use a mirror.
# Same measured rationale as 62-zeroapp: ImageBuilder passes no --build-arg, so
# the default is what a plain `agentbench evaluate` build uses. Override by
# editing the default or building the image yourself with
# `--build-arg ABB_PIP_INDEX_URL=https://pypi.org/simple/`.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/tmp \
    MPLBACKEND=Agg \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    TOKENIZERS_PARALLELISM=false

WORKDIR /opt/agent

COPY agent/ ./agent/

# Install upstream exactly as its uv.lock resolves it: export the locked base
# dependency set (no extras, no dev group) and install the package itself
# without re-resolving. The lock is universal, so markers select the Linux
# wheels here. opentelemetry-sdk is the ABB worker's observation dependency,
# declared the same way as the other validated units.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" "uv>=0.7,<1" \
    && cd agent \
    && uv export --frozen --no-dev --no-hashes --no-emit-project --output-file /tmp/requirements.txt \
    && python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
         --timeout 120 --retries 5 -r /tmp/requirements.txt \
    && python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" --no-deps . \
    && python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" "opentelemetry-sdk>=1.30,<2" \
    && rm -f /tmp/requirements.txt \
    && python -c "import openchatbi.agent_graph, openchatbi.streaming, openchatbi.observability.tracing, langchain_openai, jieba" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

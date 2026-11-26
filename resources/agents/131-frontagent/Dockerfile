FROM node:24-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir agent-client-protocol 'jsonschema>=4.23,<5' opentelemetry-sdk 'fastembed>=0.7,<1' \
    && npm install --global pnpm@9.0.0
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN CI=1 pnpm install --frozen-lockfile && pnpm build:verify \
    && pnpm exec playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 agent \
    && mkdir /workspace && chown agent:agent /workspace /home/agent
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
RUN python -c "from fastembed import TextEmbedding; m=TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/frontagent-embeddings', threads=1, providers=['CPUExecutionProvider']); assert len(next(m.embed(['hello']))) == 384" \
    && chown -R agent:agent /opt/frontagent-embeddings
FROM dependencies
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
USER agent

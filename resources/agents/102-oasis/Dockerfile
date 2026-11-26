FROM ollama/ollama@sha256:ccc42bcd3d5fcf7ab0d532b300382154e1a4da56fc666bdb313b78ebdd912754 AS dependencies
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git curl \
    libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=/opt/ollama-models CUDA_VISIBLE_DEVICES=-1 \
    OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN pip install --no-cache-dir . 'agent-client-protocol>=0.7,<1' opentelemetry-sdk jsonschema
RUN ollama serve >/tmp/ollama-build.log 2>&1 & pid=$!; \
    for attempt in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    ollama pull nomic-embed-text; result=$?; kill "$pid"; exit "$result"
RUN chown -R agent:agent /opt/ollama-models
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown -R agent:agent /workspace /opt/agent/agent
USER agent
ENTRYPOINT []

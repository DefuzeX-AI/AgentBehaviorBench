FROM neo4j:5.26-community AS neo4j-distribution
FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime:/opt/agent/agent NEO4J_HOME=/var/lib/neo4j MODEL_CACHE_ROOT=/opt/models
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless git build-essential libxml2-dev libxslt1-dev antiword unrtf poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir 'pip<24.1' \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY --from=neo4j-distribution /var/lib/neo4j /var/lib/neo4j
RUN mkdir -p /var/lib/neo4j/plugins && cp /var/lib/neo4j/labs/apoc-*.jar /var/lib/neo4j/plugins/
WORKDIR /opt/agent/agent
COPY agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
COPY agent/graphrag_agent/ ./graphrag_agent/
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/opt/models/model')" \
    && useradd --create-home --uid 10001 agent
ENV HOME=/home/agent CACHE_ROOT=/home/agent/graphrag-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_LLM_MODEL=gpt-4o-mini OPENAI_EMBEDDINGS_MODEL=text-embedding-3-small
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace && chown -R agent:agent /var/lib/neo4j
USER agent

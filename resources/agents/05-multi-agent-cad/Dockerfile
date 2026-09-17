FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    AIDER_CHECK_UPDATE=false
WORKDIR /opt/agent
COPY agent/ ./agent/
# The README's verified pure-pip workaround (aider pins numpy 1.26.4; build123d needs numpy 2).
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir "aider-chat==0.82.3" \
    && python -m pip install --no-cache-dir --no-deps --force-reinstall "numpy>=2,<2.3" \
    && python -m pip install --no-cache-dir "build123d>=0.8" "langgraph>=0.2,<0.3" "langgraph-checkpoint>=2.0,<3.0" \
       "pydantic>=2.5" "openai>=1.20.0" "anthropic>=0.30" "trimesh>=4.0" "rtree>=1.1" "scipy>=1.10" \
       "scikit-learn>=1.3" "fastapi>=0.110" "uvicorn[standard]>=0.27" "ipython>=8.15" 'opentelemetry-sdk>=1.30,<2' \
    && python -m pip install --no-cache-dir --no-deps ./agent \
    && python -c "from multi_agent_cad.graph import build_graph; build_graph()" \
    && useradd --create-home --uid 10001 agent
# nodes.py caches pipeline JSON in <repo>/pipeline_cache, which ABB mounts read-only; point it at the
# container's writable /tmp (always present at run time).
RUN rm -rf agent/pipeline_cache && ln -s /tmp agent/pipeline_cache
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

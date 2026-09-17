FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's uv.lock (consistent with pyproject.toml), installed into the interpreter ABB's worker
# runs.
RUN python -m pip install --no-cache-dir uv \
    && cd agent && uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt && cd .. \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && cd agent && python -c "import sys; sys.path.append('src'); from src.agent import Agent" && cd .. \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

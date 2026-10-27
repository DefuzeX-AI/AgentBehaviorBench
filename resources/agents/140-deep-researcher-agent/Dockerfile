FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false
WORKDIR /opt/agent
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.11.26
COPY agent/ ./agent/
RUN cd agent && uv sync --frozen --no-dev --package deep-researcher-agent --package tavily-web-search \
    && uv pip install --python /opt/venv/bin/python pip \
    && /opt/venv/bin/python -c "from nat.runtime.loader import load_workflow; import deep_researcher_agent; import langchain_tavily"
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml
RUN useradd --create-home --uid 10001 agent && chown -R agent:agent /opt/agent
# Native langchain-openai's keepalive transport otherwise ignores ABB's
# runtime-owned HTTP(S)_PROXY. Use its supported proxy-compatible setting.
ENV LANGCHAIN_OPENAI_TCP_KEEPALIVE=0
USER agent

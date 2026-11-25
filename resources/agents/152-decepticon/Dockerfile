FROM python:3.13-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates     && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/pyproject.toml agent/uv.lock ./
COPY agent/packages/ ./packages/
COPY agent/config/ ./config/
COPY agent/skills/ ./skills/
RUN uv sync --frozen --no-dev --extra openshell     && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'     && .venv/bin/python -m ensurepip --upgrade     && useradd --create-home --uid 10001 agent     && mkdir /workspace && chown agent:agent /workspace
ENV PATH=/opt/agent/agent/.venv/bin:$PATH     DECEPTICON_LLM__PROXY_URL=https://api.openai.com/v1     DECEPTICON_FORCED_MODEL=gpt-4o-mini
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent && chown agent:agent /home/agent
USER agent

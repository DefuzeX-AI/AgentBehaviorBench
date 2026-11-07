FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv==0.13.5
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime HOME=/home/agent \
    UV_PROJECT_ENVIRONMENT=/opt/fast-agent-venv UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/agent
COPY agent/ ./agent/
# The native Agent keeps its complete upstream lock in a separate environment.
# ABB's worker requirements must not replace fast-agent's pinned dependencies.
RUN cd agent && uv sync --frozen --no-dev --no-editable --package fast-agent-mcp \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
USER agent

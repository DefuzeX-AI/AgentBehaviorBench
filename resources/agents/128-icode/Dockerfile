FROM ghcr.io/astral-sh/uv@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv-runtime
FROM python:3.14.8-slim-bookworm@sha256:44e000a07b48bef1517a2b14adc93c17af728ca98858b5e24c6e1b18de1b2ef2
COPY --from=uv-runtime /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV UV_PROJECT_ENVIRONMENT=/opt/icode-venv UV_PYTHON_DOWNLOADS=never \
    PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent /opt/icode-venv
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2'
COPY bootstrap/ ./bootstrap/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
USER agent

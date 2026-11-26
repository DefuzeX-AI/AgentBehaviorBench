FROM python:3.13-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/backend
RUN apt-get update && apt-get install -y --no-install-recommends postgresql redis-server git libpq5 libsm6 libxext6     && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv==0.12.6
COPY --from=node:24-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm     && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
WORKDIR /opt/agent/agent/backend
COPY agent/backend/ ./
RUN uv sync --frozen --no-dev     && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'     && .venv/bin/python -m ensurepip --upgrade     && useradd --create-home --uid 10001 agent
ENV PATH=/opt/agent/agent/backend/.venv/bin:$PATH
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent && chown agent:agent /home/agent
USER agent

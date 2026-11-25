FROM node:24-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime READANY_HOME=/home/agent/readany
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && npm install -g pnpm@9.15.0
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN ONNXRUNTIME_NODE_INSTALL_CUDA=skip pnpm --filter @readany/cli... install --frozen-lockfile \
    && useradd --create-home --uid 10001 agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent /workspace && chown agent:agent /home/agent /workspace
USER agent

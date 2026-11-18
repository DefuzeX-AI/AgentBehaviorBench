FROM --platform=linux/amd64 node:22-bookworm-slim AS node
FROM --platform=linux/amd64 python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/abb-runtime HOME=/home/agent NODE_ENV=production
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && npm ci --omit=dev --no-audit --no-fund \
    && python -m pip install --no-cache-dir \
      -r node_modules/@structureclaw/structureclaw/backend/src/agent-skills/analysis/runtime/requirements.txt \
      'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
RUN apt-get update && apt-get install -y --no-install-recommends libquadmath0 libblas3 \
    && rm -rf /var/lib/apt/lists/* \
    && python -c "import openseespy.opensees as ops; print(ops.version())"
# ABB's Python LangGraph observer requires the host framework dependency too.
RUN python -m pip install --no-cache-dir 'langgraph>=1.0,<2'
COPY .abb-runtime/ /opt/abb-runtime/
RUN python -c "from agentbench.observe.langchain import TraceCallback; from agentbench.runtime.agentcontainer.channel import serve; print('ABB worker imports OK')"
COPY bindings/ ./bindings/
COPY network/ ./network/
COPY agent.toml ./agent.toml
USER agent

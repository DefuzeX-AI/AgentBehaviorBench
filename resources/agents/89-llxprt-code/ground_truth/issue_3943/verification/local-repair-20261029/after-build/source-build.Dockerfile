# syntax=docker/dockerfile:1.7
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep git build-essential && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv && npm install -g bun@1.3.14
ENV PATH=/opt/agent/source/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY source/ ./source/
RUN cd source && bun install --frozen-lockfile && bun run generate && bun scripts/bun-build.config.ts --cli-only
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown agent:agent /home/agent /home/agent/workspace
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml provenance.json ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
COPY regression.ts ./regression.ts
USER agent

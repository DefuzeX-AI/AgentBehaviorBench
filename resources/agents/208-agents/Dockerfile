FROM oven/bun:1.4.4-debian AS bun
FROM pgvector/pgvector:pg17-bookworm AS dependencies
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /uvx /usr/local/bin/
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv build-essential git nginx openssl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk 'langchain-core>=1,<2'
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN bun install --frozen-lockfile && bun run prisma:generate && bun run build \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown -R agent:agent /opt/agent/agent /workspace /home/agent
FROM dependencies
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
ENTRYPOINT []
CMD []

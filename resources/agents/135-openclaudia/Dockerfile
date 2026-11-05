# Multi-stage: compile OpenClaudia, then run ABB worker + print-mode binary.
# Upstream ships no verified release binary; build from the pinned source.
FROM rust:bookworm AS builder
WORKDIR /src
RUN apt-get update \
    && apt-get install -y --no-install-recommends pkg-config libssl-dev ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
COPY agent/ ./
RUN rustc --version \
    && cargo build --release --locked \
    && install -m 0755 target/release/openclaudia /usr/local/bin/openclaudia \
    && /usr/local/bin/openclaudia --help >/dev/null

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent \
    PATH=/usr/local/bin:$PATH \
    OPENCLAUDIA_BASH_SANDBOX=off

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent

COPY --from=builder /usr/local/bin/openclaudia /usr/local/bin/openclaudia

WORKDIR /opt/agent
# Observer callbacks for framework=langgraph import langchain_core.
RUN python -m pip install --no-cache-dir \
        'langchain-core>=0.3,<1.0' \
        'opentelemetry-sdk>=1.30,<2' \
        'PyYAML>=6,<7' \
        'filelock>=3.12,<4'

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
COPY network/ ./network/
COPY source-manifest.json ./source-manifest.json
COPY requirement.md ./requirement.md

# LangGraph adapter always resolves source_root to agent/; print-mode binding
# does not import upstream Python, but the directory must exist.
RUN mkdir -p /opt/agent/agent \
    && chown -R agent:agent /opt/agent
USER agent
WORKDIR /home/agent/workspace

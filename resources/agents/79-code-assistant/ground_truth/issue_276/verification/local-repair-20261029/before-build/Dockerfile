# syntax=docker/dockerfile:1.7
FROM rust:1.96-slim-trixie AS builder
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev ca-certificates git clang cmake && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY source/ ./
ENV CARGO_BUILD_JOBS=4 CARGO_PROFILE_DEV_DEBUG=0
RUN --mount=type=cache,id=abb-gt276-registry,target=/usr/local/cargo/registry --mount=type=cache,id=abb-gt276-git,target=/usr/local/cargo/git --mount=type=cache,id=abb-gt276-target,target=/src/target \
    cargo build --locked -p code-assistant --no-default-features --features acp-frontend && cp target/debug/code-assistant /code-assistant \
    && (cargo test --locked -p fs_explorer --lib > /regression.log 2>&1; echo $? > /regression.exit)
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git ripgrep libssl3t64 && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/code-assistant/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY --from=builder /code-assistant /opt/code-assistant/bin/code-assistant
COPY --from=builder /regression.log /regression.exit /opt/
RUN code-assistant --version && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml provenance.json ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

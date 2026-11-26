# zerostack (ACP over stdio) outer ABB image.
# Build context is the outer Agent unit ("."):
#   agent/        ABB's launcher (install/ applied into agent/ by source.method = "install");
#                 the upstream source is fetched below at the pinned revision
#   agent.toml    saved manifest consumed by the BBA worker
#   .abb-runtime/ injected by BBA at build time

# ---- Builder: compile the Rust CLI from the pinned source -----------------
FROM rust:1-slim-bookworm AS builder

# rust-toolchain.toml in the source pins Rust 1.96.0 (rustup fetches it during
# the build) and .cargo/config.toml selects mold as the linker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config mold git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Fetch exactly the pinned upstream commit (no submodules: the `tap` submodule is
# a Homebrew tap and is not a build input). ABB's Git source mode rejects
# submodules, so the unit uses install mode and the build fetches the source.
ARG ZEROSTACK_REVISION=797dca9c0c4ddb16e09e9707ca17634b13f878ea
WORKDIR /build/agent
RUN git init -q . \
    && git remote add origin https://github.com/gi-dellav/zerostack.git \
    && git fetch -q --depth 1 origin "$ZEROSTACK_REVISION" \
    && git checkout -q FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$ZEROSTACK_REVISION"
# The ACP server is gated behind the `acp` feature (agent-client-protocol +
# blocking), which is not in default features. --locked honors Cargo.lock.
RUN cargo build --locked --release --features acp

# ---- Runtime: BBA Python worker plus the zerostack ACP binary --------------
FROM debian:bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

# python3/python3-pip/python-is-python3 provide the `python` interpreter used
# by launch.argv, the ACP adapter command and the SDK overlay's `python -m pip`;
# bash and git back zerostack's terminal tools. The PEP 668 marker is removed because ABB's SDK overlay
# runs `python -m pip --isolated install` (ignores PIP_BREAK_SYSTEM_PACKAGES). BBA's runtime staging installs
# the worker bootstrap and ACP adapter requirements into this interpreter.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates git bash python3 python3-pip python-is-python3 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/lib/python3*/EXTERNALLY-MANAGED \
    && useradd --create-home --uid 10001 agent

COPY --from=builder /build/agent/target/release/zerostack /usr/local/bin/zerostack
RUN zerostack --version

WORKDIR /opt/agent
# agent/ holds the install/ inputs; delivers /opt/agent/agent/abb-acp-launch.py.
COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

# adapter.cwd from agent.toml: writable ACP workspace for the final user;
# HOME /home/agent is created and owned via useradd --create-home above.
RUN mkdir -p /workspace/project \
    && chown agent:agent /workspace/project

USER agent

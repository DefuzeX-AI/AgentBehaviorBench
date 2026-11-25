# syntax=docker/dockerfile:1

# Stage 1: Build React dashboard
# Pinned to a specific minor (not floating `node:22-alpine`) so rebuilds of a tagged release months later produce a bit-for-bit identical builder image.
# Node 22 LTS is the floor pnpm 11+ supports, and 22.12+ is what vite 8 requires.
FROM node:22.23.3-alpine AS dashboard-builder
WORKDIR /build
COPY agent/crates/librefang-api/dashboard ./dashboard
WORKDIR /build/dashboard
# `corepack enable` alone hits `fetchLatestStableVersion2` against the npm
# registry, which has flaked on us during builds. Activate the pinned pnpm
# version (matches the `packageManager` field in package.json) directly so
# the build never has to ask the registry "what's the latest stable?".
# We also refresh corepack itself first: the keyring bundled with the node
# base image goes stale as pnpm rotates signing keys, manifesting as
# "Internal Error: Cannot find matching keyid" during `corepack prepare`.
# Node ≥20.19 is also required by vite 8 / rolldown's optional native
# bindings (engines: ^20.19.0), without which `pnpm install` silently skips
# the linux-x64-musl binding and `vite build` fails at require-time.
# Dependency lifecycle scripts are intentionally disabled in this build
# stage. Vite/rolldown and esbuild ship their musl binaries through pinned
# optional dependencies, so the dashboard build needs no postinstall code.
RUN npm install --global corepack@0.34.6 \
    && corepack enable \
    && corepack prepare pnpm@12.6.0 --activate \
    && pnpm install --frozen-lockfile --ignore-scripts \
    && pnpm run build

# Stage 2: Build Rust binary
# Pinned to a specific minor (not floating `rust:1-slim-bookworm`). Tracks the
# workspace MSRV declared in Cargo.toml's [workspace.package].rust-version
# (currently 1.95.0) so the build image is guaranteed to satisfy it.
FROM rust:1.95-slim-bookworm AS builder
WORKDIR /build
# libdbus-1-dev is required by libdbus-sys (transitive dep of keyring's
# sync-secret-service feature, added in #3180). Without it the cargo build
# panics with exit 101 in the build script — same root cause as #3259, and
# why the v2026.4.27-beta6 docker image was never published.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    libdbus-1-dev \
    perl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY agent/Cargo.toml agent/Cargo.lock ./
COPY agent/crates ./crates
COPY agent/xtask ./xtask
COPY agent/packages ./packages
# librefang-channels embeds the Python SDK tree at compile time via
# include_dir!("$CARGO_MANIFEST_DIR/../../sdk/python/librefang") in
# embedded_sdk.rs (added in #5472). Without this COPY the proc macro
# panics with "sdk/python/librefang is not a directory". Only this one
# subtree is needed — .dockerignore keeps the rest of sdk/ out.
COPY agent/sdk/python/librefang ./sdk/python/librefang
# The same module reads the SDK version out of `sdk/python/pyproject.toml` with include_str!, because the extracted tree has neither a sibling pyproject.toml nor installed package metadata and would answer `0+unknown`.
# Without this COPY the build fails with "couldn't read crates/librefang-channels/src/../../../sdk/python/pyproject.toml".
COPY agent/sdk/python/pyproject.toml ./sdk/python/pyproject.toml
# librefang-api uses include_str!("../../../deploy/...") to embed the
# observability stack (prometheus / tempo / otel-collector / grafana
# configs) at compile time — added in #3062. Without this COPY the
# build fails with "couldn't read deploy/grafana/...". flake.nix
# already lists the same paths in its source fileset.
COPY agent/deploy ./deploy
COPY --from=dashboard-builder /build/static/react ./crates/librefang-api/static/react

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    --mount=type=cache,target=/build/target \
    # `--features telemetry`: the published Docker image is the full
    # daemon, so it ships with telemetry on. Channel adapters all run as
    # out-of-process sidecars now (see #5408 / #5461), so the old
    # `all-channels` / `core-channels` aliases are gone — `telemetry` is
    # the whole opt-in surface left, matching the CLI's own `default`.
    CARGO_BUILD_JOBS=2 cargo build --locked --release --bin librefang --features telemetry && \
    cp target/release/librefang /usr/local/bin/librefang

# Node remains in the runtime image for JavaScript sidecars such as the
# WhatsApp gateway copied under /opt/librefang/packages.
# Pinned to a specific Node 22 LTS minor (not floating `node:lts-bookworm-slim`)
# so a rebuild months later doesn't quietly land on a new major when the
# `lts` alias rolls forward. `curl` is added for the HEALTHCHECK below.
FROM node:24-bookworm-slim AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep python3 python3-venv libicu72 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir tomli-w 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
COPY --from=builder /usr/local/bin/librefang /usr/local/bin/librefang
COPY --from=builder /build/packages /opt/librefang/packages
ENV HOME=/home/agent LIBREFANG_HOME=/home/agent/.librefang PYTHONPATH=/opt/abb-runtime
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent
RUN librefang init --quick
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

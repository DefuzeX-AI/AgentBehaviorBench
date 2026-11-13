# Build the selected upstream commit from its own Cargo.lock, vendored patches/
# crates and pinned toolchain (rust-toolchain.toml: 1.98.1), with the command
# build-linux-windows.yml uses for the shipped Linux binaries:
# `cargo build --locked --profile release-fast --features allocator-jemalloc`
# and RUSTFLAGS `-C link-arg=-Wl,--gc-sections`.
FROM rust:1.98.1-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev libdbus-1-dev \
    && rm -rf /var/lib/apt/lists/*
# Selecting the pinned toolchain explicitly skips the file's optional components
# (rust-src, rust-analyzer, ...) and extra targets, which the build does not use.
ENV RUSTUP_TOOLCHAIN=1.98.1 CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TERM_COLOR=never \
    RUSTFLAGS="-C link-arg=-Wl,--gc-sections"
WORKDIR /src
COPY agent/ ./
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-vtcode-target,target=/src/target,sharing=locked \
    cargo build --locked --profile release-fast --features allocator-jemalloc \
    && install -D -m 0755 target/release-fast/vtcode /out/vtcode

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/vtcode/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/vtcode /opt/vtcode/bin/vtcode
RUN ! ldd /opt/vtcode/bin/vtcode | grep 'not found' \
    && USER=agent /opt/vtcode/bin/vtcode --version > /dev/null && rm -rf /root/.config /root/.local /root/.cache \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY provenance.json ./provenance.json
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Build the selected upstream commit from its own Cargo.lock, vendored patches/
# crates and the toolchain its rust-toolchain.toml pins, with the command
# build-linux-windows.yml uses for the shipped Linux binaries:
# `cargo build --locked --profile release-fast --features allocator-jemalloc`
# and RUSTFLAGS `-C link-arg=-Wl,--gc-sections`.
FROM rust:1.98.1-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends pkg-config libssl-dev libdbus-1-dev \
    && rm -rf /var/lib/apt/lists/*
# Used only when the commit has no toolchain file or says "stable".
ARG STABLE_TOOLCHAIN=1.98.1
ENV CARGO_BUILD_JOBS=4 CARGO_INCREMENTAL=0 CARGO_TERM_COLOR=never \
    RUSTFLAGS="-C link-arg=-Wl,--gc-sections"
WORKDIR /src
COPY agent/ ./
# Source mtimes come from the exported tree and can be older than the cached
# target's fingerprints, so the source is touched first: cached dependencies
# are reused, but the workspace crates are always rebuilt from this source.
# The toolchain is installed with the minimal profile; the file's extra
# components (rust-src, rust-analyzer, ...) are not used by the build.
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-vtcode-target,target=/src/target,sharing=locked \
    set -eu \
    && tc=$(sed -n 's/^[[:space:]]*channel[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' rust-toolchain.toml rust-toolchain 2>/dev/null | head -n 1) \
    && if [ -z "$tc" ] && [ -f rust-toolchain ]; then tc=$(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' rust-toolchain | head -n 1 | tr -d '[:space:]'); fi \
    && case "$tc" in ''|stable) tc="$STABLE_TOOLCHAIN" ;; esac \
    && rustup toolchain install --profile minimal --no-self-update "$tc" \
    && export RUSTUP_TOOLCHAIN="$tc" \
    && find /src -path /src/target -prune -o -type f -exec touch {} + \
    && cargo build --locked --profile release-fast --features allocator-jemalloc \
    && install -D -m 0755 target/release-fast/vtcode /out/vtcode

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
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

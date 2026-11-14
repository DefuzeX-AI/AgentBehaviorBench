# Build the selected upstream commit from its own Cargo.lock and the toolchain
# its rust-toolchain.toml pins, the way release-agent.yml builds the shipped
# `peri` binary: `scripts/cargo-rmcp-patched.sh build --locked -p peri-tui --release`.
# The script applies the repository's rmcp/hyper-util patches before Cargo runs.
# The release archive also carries the Bun-built workflow sidecar
# (peri-resources/workflow/); it is not built here, and neither image has the
# Node.js runtime it needs.
FROM rust:1.98.1-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends patch pkg-config libssl-dev \
        libxcb1-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev \
    && rm -rf /var/lib/apt/lists/*
# The release uses fat LTO, whose single-process link is OOM-killed in an 8 GB
# Docker VM. Thin LTO keeps the rest of the release profile (opt-level z,
# codegen-units 1, strip) and only changes cross-crate optimization; machines
# with more memory can pass --build-arg PERI_RELEASE_LTO=fat.
ARG PERI_RELEASE_LTO=thin
# Used only when the commit has no toolchain file or says "stable".
ARG STABLE_TOOLCHAIN=1.98.1
ENV CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never CARGO_PROFILE_RELEASE_LTO=$PERI_RELEASE_LTO
WORKDIR /src
COPY agent/ ./
# Source mtimes come from the exported tree and can be older than the cached
# target's fingerprints, so the source is touched first: cached dependencies
# are reused, but the workspace crates are always rebuilt from this source.
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-peri-target,target=/src/target,sharing=locked \
    set -eu \
    && tc=$(sed -n 's/^[[:space:]]*channel[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' rust-toolchain.toml rust-toolchain 2>/dev/null | head -n 1) \
    && if [ -z "$tc" ] && [ -f rust-toolchain ]; then tc=$(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' rust-toolchain | head -n 1 | tr -d '[:space:]'); fi \
    && case "$tc" in ''|stable) tc="$STABLE_TOOLCHAIN" ;; esac \
    && rustup toolchain install --profile minimal --no-self-update "$tc" \
    && export RUSTUP_TOOLCHAIN="$tc" \
    && find /src -path /src/target -prune -o -type f -exec touch {} + \
    && ./scripts/cargo-rmcp-patched.sh build --locked -p peri-tui --release \
    && install -D -m 0755 target/release/peri /out/peri

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/peri/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/peri /opt/peri/bin/peri
RUN ! ldd /opt/peri/bin/peri | grep 'not found' && /opt/peri/bin/peri --version \
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

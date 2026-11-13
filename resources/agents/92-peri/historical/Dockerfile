# Build the selected upstream commit from its own Cargo.lock and pinned toolchain
# (rust-toolchain.toml), the way release-agent.yml builds the shipped `peri`
# binary: `scripts/cargo-rmcp-patched.sh build --locked -p peri-tui --release`.
# The script applies the repository's rmcp/hyper-util patches before Cargo runs.
# The release archive also carries the Bun-built workflow sidecar
# (peri-resources/workflow/); it is not built here, and neither image has the
# Node.js runtime it needs.
FROM rust:1.99.0-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends patch pkg-config libssl-dev \
        libxcb1-dev libxkbcommon-dev libxkbcommon-x11-dev libwayland-dev \
    && rm -rf /var/lib/apt/lists/*
# The toolchain file pins 1.99.0; selecting it explicitly skips its optional
# rustfmt/clippy components, which the build does not use.
# The release profile's fat LTO link (one rustc process) is OOM-killed in an
# 8 GB Docker VM; thin LTO keeps the rest of the release profile (opt-level z,
# codegen-units 1, strip) and only changes cross-crate optimization.
ENV RUSTUP_TOOLCHAIN=1.99.0 CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never CARGO_PROFILE_RELEASE_LTO=thin
WORKDIR /src
COPY agent/ ./
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-peri-target,target=/src/target,sharing=locked \
    ./scripts/cargo-rmcp-patched.sh build --locked -p peri-tui --release \
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

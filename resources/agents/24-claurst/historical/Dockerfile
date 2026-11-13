# Build the selected Claurst commit (Cargo workspace in src-rust/) from its own
# Cargo.lock, then install it where the default image puts the release binary
# (/opt/claurst/bin). Builder and runtime share node:24-trixie (same glibc).
FROM node:24-trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git build-essential pkg-config cmake clang libclang-dev \
        libssl-dev libasound2-dev perl \
    && rm -rf /var/lib/apt/lists/*
# The repository has no rust-toolchain file and its release workflow uses
# dtolnay/rust-toolchain@stable: pin the stable release that was current when
# the GT commit was released (v0.1.7, 2026-07). A toolchain file, if present, wins.
ARG RUST_STABLE=1.96.0
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH \
    CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never CARGO_INCREMENTAL=0
RUN curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path \
        --default-toolchain "$RUST_STABLE"
WORKDIR /src
COPY agent/ ./
# Same command as the upstream release workflow (default features, incl. voice).
# Exp3 builds the baseline and then the repaired source with the same cached
# target/; copied sources keep their old mtimes, so touch them first or Cargo
# would reuse the baseline's workspace crates. Dependencies stay cached.
RUN --mount=type=cache,id=abb-claurst-cargo-registry,target=/opt/cargo/registry \
    --mount=type=cache,id=abb-claurst-cargo-git,target=/opt/cargo/git \
    --mount=type=cache,id=abb-claurst-target,target=/src/src-rust/target \
    find /src -path /src/src-rust/target -prune -o -type f -exec touch {} + \
    && cd src-rust \
    && channel=$(sed -n 's/^channel *= *"\(.*\)"/\1/p' rust-toolchain.toml ../rust-toolchain.toml 2>/dev/null | head -1 || true) \
    && if [ -z "$channel" ] || [ "$channel" = stable ]; then export RUSTUP_TOOLCHAIN="$RUST_STABLE"; fi \
    && cargo build --release --locked --package claurst \
    && mkdir -p /out && cp target/release/claurst /out/claurst

FROM node:24-trixie
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl libasound2t64 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/claurst/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/claurst /opt/claurst/bin/claurst
RUN chmod 0755 /opt/claurst/bin/claurst && /opt/claurst/bin/claurst --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent \
    && chmod 0755 /home/agent && chmod 0777 /home/agent/workspace
COPY provenance.json ./provenance.json
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

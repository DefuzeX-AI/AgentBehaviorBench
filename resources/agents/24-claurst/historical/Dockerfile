# Build the selected Claurst commit (Cargo workspace in src-rust/) from its own
# Cargo.lock, then install it where the default image puts the release binary
# (/opt/claurst/bin). Builder and runtime are both Debian trixie (same glibc).
# No rust-toolchain file at the GT commit; the release used `stable`, which was 1.96.0 at v0.1.7 (2026-07).
FROM rust:1.96.0-trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake clang libclang-dev libssl-dev libasound2-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ENV CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never CARGO_INCREMENTAL=0
WORKDIR /src
COPY agent/ ./
# Same command as the upstream release workflow (default features, incl. voice).
# Exp3 builds the baseline and then the repaired source with the same cached
# target/; copied sources keep their old mtimes, so touch them first or Cargo
# would reuse the baseline's workspace crates. Dependencies stay cached.
RUN --mount=type=cache,id=abb-claurst-cargo-registry,target=/usr/local/cargo/registry \
    --mount=type=cache,id=abb-claurst-cargo-git,target=/usr/local/cargo/git \
    --mount=type=cache,id=abb-claurst-target,target=/src/src-rust/target,sharing=locked \
    find /src -path /src/src-rust/target -prune -o -type f -exec touch {} + \
    && cd src-rust \
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

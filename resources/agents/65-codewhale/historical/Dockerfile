# Build the selected upstream commit from its own Cargo.lock, the way
# release-artifacts.yml builds the shipped Linux binary:
# `cargo build --profile dist --locked --target <arch>-unknown-linux-musl -p codewhale-cli`.
# rust-toolchain.toml says "stable"; the image pins 1.98.1 (the 1.98 line was
# stable when this commit landed), so the build does not drift with time.
FROM rust:1.98.1-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends musl-tools \
    && rm -rf /var/lib/apt/lists/*
# The codewhale-tui crate (~790k lines) needs more than 6 GB of rustc memory in
# its front end alone, whatever the LTO, codegen-unit or job settings, so this
# build needs a Docker VM with well over 8 GB of memory (GitHub runners: 16 GB).
ENV RUSTUP_TOOLCHAIN=1.98.1 CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never
WORKDIR /src
COPY agent/ ./
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-codewhale-target,target=/src/target,sharing=locked \
    target="$(uname -m)-unknown-linux-musl" \
    && rustup target add "$target" \
    && cargo build --profile dist --locked --target "$target" -p codewhale-cli \
    && install -D -m 0755 "target/$target/dist/codewhale" /out/codewhale

# Same runtime base as the default image. The npm package installs the native
# binary at node_modules/codewhale/bin/downloads/, which bootstrap/launch.py
# executes directly; the package files come from this commit's npm/codewhale.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/codewhale /opt/agent/agent/node_modules/codewhale/bin/downloads/codewhale
RUN cd agent && cp -R npm/codewhale/. node_modules/codewhale/ \
    && cp node_modules/codewhale/bin/downloads/codewhale node_modules/codewhale/bin/downloads/codew \
    && node_modules/codewhale/bin/downloads/codewhale --version \
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

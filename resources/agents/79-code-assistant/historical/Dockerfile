# Build the selected code-assistant commit from its own Cargo.lock, then install
# it where the default image puts the release binary (/opt/code-assistant/bin).
# Builder and runtime are both Debian trixie (same glibc).
FROM buildpack-deps:trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake clang libclang-dev libssl-dev libzstd-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
# The repository has no rust-toolchain file and its release workflow installs
# `stable`: pin the stable release that was current when the GT commit was
# released (v0.2.16, 2026-09). A toolchain file, if present, wins.
ARG RUST_STABLE=1.98.0
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH \
    CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never CARGO_INCREMENTAL=0
RUN curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path \
        --default-toolchain "$RUST_STABLE"
WORKDIR /src
COPY agent/ ./
# The release binary is a workspace build with every default feature, including
# the gpui desktop UI. ABB only uses `code-assistant acp`, so build the binary
# headless (upstream's documented --no-default-features path) with the ACP and
# terminal frontends and document conversion; gpui and the MCP server mode are
# left out.
RUN --mount=type=cache,id=abb-code-assistant-cargo-registry,target=/opt/cargo/registry \
    --mount=type=cache,id=abb-code-assistant-cargo-git,target=/opt/cargo/git \
    --mount=type=cache,id=abb-code-assistant-target,target=/src/target \
    channel=$(sed -n 's/^channel *= *"\(.*\)"/\1/p' rust-toolchain.toml 2>/dev/null || true) \
    && if [ -z "$channel" ] || [ "$channel" = stable ]; then export RUSTUP_TOOLCHAIN="$RUST_STABLE"; fi \
    && cargo build --release --locked --package code-assistant --no-default-features \
        --features acp-frontend,terminal-frontend,document-conversion \
    && mkdir -p /out && cp target/release/code-assistant /out/code-assistant

FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
        libssl3t64 zlib1g \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/code-assistant/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/code-assistant /opt/code-assistant/bin/code-assistant
RUN chmod 0755 /opt/code-assistant/bin/code-assistant \
    && /opt/code-assistant/bin/code-assistant --version \
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

# Build the selected OpenCrabs commit from its own source and Cargo.lock, then
# install it where the default image puts the release binary (/opt/opencrabs/bin).
# Builder and runtime share ubuntu:26.04 so the binary links the same glibc.
FROM ubuntu:26.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git build-essential pkg-config cmake clang libclang-dev \
        libssl-dev libasound2-dev perl \
    && rm -rf /var/lib/apt/lists/*
# The commit's rust-toolchain.toml decides the toolchain; channel = "stable"
# resolves to the stable release that was current at v0.5.12/v0.5.13 (2026-10).
# This recipe covers all 4 opencrabs GT commits: 0dfe3b7 (v0.5.13) and 2cf3e6e
# (v0.5.12) were built and run; 685814d (v0.5.3, Issue 1704) and 212e134
# (v0.5.4, Issue 1932) were checked statically (same toolchain file, bin, release
# profile, features and RTK version) but not built. rustup (not a rust:<ver>
# image) keeps the builder on the runtime's Ubuntu 26.04 glibc and honors the file.
ARG RUST_STABLE=1.99.0
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH \
    CARGO_TERM_COLOR=never CARGO_INCREMENTAL=0
RUN curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path \
        --default-toolchain "$RUST_STABLE"
# Upstream's release builds `--release --all-features` (fat LTO; thin on
# linux-arm64 because fat LTO needs >14 GB). The opencrabs crate alone needs
# ~5.2 GB in rustc's frontend; at opt-level 3 LLVM then pushes it past an 8 GB
# Docker VM (OOM with thin LTO, without LTO, and with 1 job alike). So build
# without LTO, one job at a time, and compile only the opencrabs crate at
# opt-level 0 with 256 codegen units (measured peak ~6.6 GB); every dependency
# keeps opt-level 3, and debug assertions and overflow checks stay off as in the
# release profile. These are optimization settings only; they do not change
# program behavior. Override the ARGs on a larger host to match the release.
ARG CARGO_PROFILE_RELEASE_LTO=off
ARG CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
ARG OPENCRABS_OPT_LEVEL=0
ARG OPENCRABS_CODEGEN_UNITS=256
ARG CARGO_BUILD_JOBS=1
WORKDIR /src
COPY agent/ ./
# Exp3 builds the baseline and then the repaired source with the same cached
# target/; copied sources keep their old mtimes, so touch them first or Cargo
# would reuse the baseline's workspace crates. Dependencies stay cached.
RUN --mount=type=cache,id=abb-opencrabs-cargo-registry,target=/opt/cargo/registry \
    --mount=type=cache,id=abb-opencrabs-cargo-git,target=/opt/cargo/git \
    --mount=type=cache,id=abb-opencrabs-target,target=/src/target,sharing=locked \
    find /src -path /src/target -prune -o -type f -exec touch {} + \
    && channel=$(sed -n 's/^channel *= *"\(.*\)"/\1/p' rust-toolchain.toml 2>/dev/null || true) \
    && if [ -z "$channel" ] || [ "$channel" = stable ]; then export RUSTUP_TOOLCHAIN="$RUST_STABLE"; fi \
    && cargo build --release --locked --all-features --bin opencrabs \
        --config "profile.release.package.opencrabs.opt-level=$OPENCRABS_OPT_LEVEL" \
        --config "profile.release.package.opencrabs.codegen-units=$OPENCRABS_CODEGEN_UNITS" \
    && mkdir -p /out && cp target/release/opencrabs /out/opencrabs
# The release archive bundles the rtk helper (a separate upstream project) at the
# version pinned in the commit's release workflow; fetch that exact asset.
ARG TARGETARCH
RUN version=$(sed -n 's/^ *RTK_VERSION="\([^"]*\)".*/\1/p' .github/workflows/release.yml | head -1) \
    && test "$version" = 0.40.0 \
    && case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
         amd64) asset=rtk-x86_64-unknown-linux-musl.tar.gz; sha=a75d210a445874106bc16da2b4efba01d36d297afa33ec134728f2d5f42ef5af ;; \
         arm64) asset=rtk-aarch64-unknown-linux-gnu.tar.gz; sha=1d0087ad62a182c0833c2251ac678b5e05356418d91aa57305ac51a126c9b102 ;; \
         *) echo "unsupported architecture" >&2; exit 1 ;; \
       esac \
    && mkdir -p /tmp/rtk && curl -fsSL --retry 3 -o /tmp/rtk/rtk.tar.gz \
        "https://github.com/rtk-ai/rtk/releases/download/v$version/$asset" \
    && echo "$sha  /tmp/rtk/rtk.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/rtk/rtk.tar.gz -C /tmp/rtk \
    && cp "$(find /tmp/rtk -type f -name rtk | head -1)" /out/rtk

FROM ubuntu:26.04
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git ripgrep libgomp1 libasound2t64 python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:/opt/opencrabs/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/ /tmp/opencrabs/
RUN mkdir -p /opt/opencrabs/bin \
    && install -m 0755 /tmp/opencrabs/opencrabs /tmp/opencrabs/rtk /opt/opencrabs/bin/ && rm -rf /tmp/opencrabs \
    && /opt/opencrabs/bin/opencrabs --version \
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

# Build the selected upstream commit from its own Cargo.lock, the way its
# release workflow builds the shipped Linux binaries:
# - with a [profile.dist] (0.9.x and later, release-artifacts.yml): one binary,
#   `cargo build --profile dist --locked --target <arch>-unknown-linux-musl -p codewhale-cli`;
# - without it (0.8.x to 0.9.0, release.yml): two binaries,
#   `cargo build --release --locked --target <target> -p codewhale-cli -p codewhale-tui`,
#   where `codewhale serve` runs the codewhale-tui binary next to it. Those
#   releases shipped aarch64 Linux as gnu (x86_64 as musl from 0.8.6x on); this
#   recipe builds that layout for gnu. The gnu build links libdbus (keyring), so
#   the build stage has libdbus-1-dev and pkg-config, as release.yml installs,
#   and the runtime stage has libdbus-1-3.
# rust-toolchain.toml says "stable" (or is absent before 0.8.6x); STABLE_TOOLCHAIN
# pins it so the build does not drift with time.
#
# The codewhale-tui crate (~790k lines) needs more than 6 GB of rustc memory in
# its front end alone, whatever the LTO, codegen-unit or job settings, so this
# build needs a Docker VM with well over 8 GB of memory (GitHub runners: 16 GB).
FROM rust:1.98.1-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends musl-tools libdbus-1-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ARG STABLE_TOOLCHAIN=1.98.1
ENV CARGO_BUILD_JOBS=4 CARGO_TERM_COLOR=never
WORKDIR /src
COPY agent/ ./
# Source mtimes come from the exported tree and can be older than the cached
# target's fingerprints, so the source is touched first: cached dependencies
# are reused, but the workspace crates are always rebuilt from this source.
RUN --mount=type=cache,id=abb-hist-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=abb-hist-cargo-git,target=/usr/local/cargo/git,sharing=locked \
    --mount=type=cache,id=abb-hist-codewhale-target,target=/src/target,sharing=locked \
    set -eu \
    && tc=$(sed -n 's/^[[:space:]]*channel[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' rust-toolchain.toml rust-toolchain 2>/dev/null | head -n 1) \
    && if [ -z "$tc" ] && [ -f rust-toolchain ]; then tc=$(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' rust-toolchain | head -n 1 | tr -d '[:space:]'); fi \
    && case "$tc" in ''|stable) tc="$STABLE_TOOLCHAIN" ;; esac \
    && rustup toolchain install --profile minimal --no-self-update "$tc" \
    && export RUSTUP_TOOLCHAIN="$tc" \
    && if grep -q '^\[profile\.dist\]' Cargo.toml; then \
           profile=dist; target="$(uname -m)-unknown-linux-musl"; \
           packages="-p codewhale-cli"; bins=codewhale; \
       else \
           profile=release; target="$(uname -m)-unknown-linux-gnu"; \
           packages="-p codewhale-cli -p codewhale-tui"; bins="codewhale codewhale-tui"; \
       fi \
    && rustup target add "$target" \
    && find /src -path /src/target -prune -o -type f -exec touch {} + \
    && cargo build --profile "$profile" --locked --target "$target" $packages \
    && for b in $bins; do install -D -m 0755 "target/$target/$profile/$b" "/out/$b"; done

# Same runtime base as the default image. bootstrap/launch.py executes the
# binary at agent/node_modules/codewhale/bin/downloads/codewhale directly (where
# the npm package's installer puts it), so the built binaries go there.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/ /opt/agent/agent/node_modules/codewhale/bin/downloads/
RUN ! ldd agent/node_modules/codewhale/bin/downloads/* | grep 'not found' \
    && agent/node_modules/codewhale/bin/downloads/codewhale --version \
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

# Build the selected upstream commit's single Rust runtime (`codewhale`, which
# carries the native ACP server `codewhale serve --acp`) from its committed
# Cargo.lock, as upstream's own Dockerfile does (`cargo build --release --locked
# -p codewhale-cli`). The binary is placed where the npm package's installer puts
# it in the release image (agent/node_modules/codewhale/bin/downloads/codewhale),
# which is the path bootstrap/launch.py execs.
FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
      pkg-config libdbus-1-dev \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none --no-modify-path
# rust-toolchain.toml at the commit selects the toolchain; rustup installs it on first use.
# codewhale-tui is a single ~790k-line crate whose rustc invocation alone exhausted an
# 8 GB Docker VM at the release profile (and at opt-level 1): it is killed in LLVM code
# generation while the type-checked crate is still resident. One job, no LTO, many
# small codegen units and opt-level 0 keep it inside that budget (code generation
# only; the program's behavior is unchanged).
ENV PATH=/opt/venv/bin:/root/.cargo/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo \
    CARGO_BUILD_JOBS=1 CARGO_PROFILE_RELEASE_LTO=false CARGO_PROFILE_RELEASE_CODEGEN_UNITS=256 \
    CARGO_PROFILE_RELEASE_OPT_LEVEL=0 CARGO_INCREMENTAL=0
WORKDIR /opt/agent
COPY agent/ ./agent/
# The target dir and cargo registry are BuildKit cache mounts (as upstream's own
# Dockerfile does) so a retried build reuses compiled dependencies; only the binary
# leaves the cache.
RUN --mount=type=cache,id=abb-codewhale-hist-target,target=/opt/agent/agent/target,sharing=locked \
    --mount=type=cache,id=abb-codewhale-hist-registry,target=/root/.cargo/registry,sharing=locked \
    cd agent && cargo build --release --locked -p codewhale-cli \
    && install -D -m 0755 target/release/codewhale node_modules/codewhale/bin/downloads/codewhale \
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

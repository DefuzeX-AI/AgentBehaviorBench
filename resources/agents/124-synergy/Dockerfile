FROM oven/bun:1.4.3@sha256:ec06c3b6cea04192ae6770c434f668ca41d343ad19fa6472216c7b48be39c598 AS bun-runtime
FROM rust:1.96.1-slim-bookworm@sha256:e18a79fc84dfcfc3ab5ba72290398a644c135c97eaa881447fddc354ee4701a3 AS native-build
WORKDIR /build
COPY agent/packages/local-runtime/src/sandbox/helper-linux/ ./sandbox/
COPY agent/packages/local-runtime/src/process/native-pty/ ./pty/
RUN cargo build --release --locked --manifest-path sandbox/Cargo.toml \
    && cargo build --release --locked --manifest-path pty/Cargo.toml
FROM node:24-bookworm
COPY --from=bun-runtime /usr/local/bin/bun /usr/local/bin/bun
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep bubblewrap ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && ELECTRON_SKIP_BINARY_DOWNLOAD=1 bun install --frozen-lockfile \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
RUN cd agent && bun packages/local-runtime/script/build-watcher.ts --local
COPY --from=native-build /build/sandbox/target/release/synergy-sandbox-linux /opt/agent/agent/packages/local-runtime/src/sandbox/helper-linux/target/release/synergy-sandbox-linux
COPY --from=native-build /build/pty/target/release/libsynergy_pty.so /opt/agent/agent/packages/local-runtime/.artifacts/pty/linux-x64-glibc/libsynergy_pty.so
COPY bootstrap/ ./bootstrap/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
USER agent

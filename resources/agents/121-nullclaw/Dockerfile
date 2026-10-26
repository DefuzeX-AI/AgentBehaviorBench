# Outer ABB image for the nullclaw Agent unit (nullclaw/nullclaw @ 5f1cade05c19, version 2026.5.29).
# Hand-written from the upstream Dockerfile's builder stage (alpine + the repo's own .github/scripts/install-zig.sh
# for Zig 0.16.0, static target-platform Linux-musl ReleaseSmall build) plus a Debian runtime that carries python3 for the
# BBA worker / ACP launcher / SDK overlay.

# -- Stage 1: build the static nullclaw binary from the pinned source ------------------------------------------------
FROM alpine:3.24 AS builder
RUN apk add --no-cache bash curl git musl-dev python3
WORKDIR /app
# Copy the whole restored source (ABB validates COPY sources before the source is restored, so
# individual agent/ paths would fail on a fresh checkout).
COPY agent/ ./
RUN set -eu; mkdir -p /tmp/zig-path; \
    GITHUB_PATH=/tmp/zig-path/path RUNNER_TEMP=/opt bash .github/scripts/install-zig.sh 0.16.0; \
    ln -sf "$(cat /tmp/zig-path/path)/zig" /usr/local/bin/zig; test "$(zig version)" = "0.16.0"
ARG TARGETARCH
RUN set -eu; case "$TARGETARCH" in \
      amd64) zig_target=x86_64-linux-musl ;; \
      arm64) zig_target=aarch64-linux-musl ;; \
      *) echo "Unsupported target architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    zig build -Dtarget="$zig_target" -Doptimize=ReleaseSmall -Dversion=5f1cade05c19 \
    && cp zig-out/bin/nullclaw /usr/local/bin/nullclaw && rm -rf zig-out .zig-cache /root/.cache/zig

# -- Stage 2: runtime -------------------------------------------------------------------------------------------------
FROM debian:bookworm-slim
# curl: nullclaw's provider HTTP path; git: agent tool; python3/pip: BBA worker, ACP launcher, SDK overlay.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git python3 python3-pip python-is-python3 \
    && rm -rf /var/lib/apt/lists/* && rm -f /usr/lib/python3*/EXTERNALLY-MANAGED
COPY --from=builder /usr/local/bin/nullclaw /usr/local/bin/nullclaw
RUN nullclaw --version

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

# Non-root runtime user; /workspace/project is adapter.cwd and [evaluation.workspace].path.
# The system CA bundle is made writable by the agent user so the launcher can append ABB's interception CA
# (the Zig std HTTP client ignores SSL_CERT_FILE).
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/project \
    && chown -R agent:agent /workspace \
    && chown agent:agent /etc/ssl/certs/ca-certificates.crt
ENV HOME=/home/agent

WORKDIR /opt/agent
# agent/ = pinned source with install/abb-acp-launch.py applied by source preparation.
COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

USER agent
# No ENTRYPOINT/CMD: BBA launches `python -m agentbench.runtime.agentcontainer.worker` from /opt/agent.

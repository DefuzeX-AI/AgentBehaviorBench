# Build the selected upstream commit from source the way its release workflow
# builds the Linux binary: pinned Zig 0.17.0 (build.zig.zon minimum_zig_version),
# `zig build -Doptimize=ReleaseSafe -Dtarget=<arch>-linux`. `zig build` fetches
# whatever build.zig.zon declares at build time.
FROM debian:bookworm-slim AS build
ARG TARGETARCH
ARG ZIG_VERSION=0.17.0
ARG ZIG_SHA256_X86_64=1cbe9df9f27e6b78d14ccbca43b6703a404ef79ef1c463de901d7f088d4e2026
ARG ZIG_SHA256_AARCH64=9e8d11661d4ae3bd57702a3832781e23ad151dde5798e16a5ccd503f65234ff8
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
ENV ZIG_GLOBAL_CACHE_DIR=/tmp/zig-global ZIG_LOCAL_CACHE_DIR=/tmp/zig-local
RUN arch="${TARGETARCH:-$(uname -m)}" \
    && case "$arch" in \
         amd64|x86_64) zarch=x86_64; sha="$ZIG_SHA256_X86_64" ;; \
         arm64|aarch64) zarch=aarch64; sha="$ZIG_SHA256_AARCH64" ;; \
         *) echo "unsupported architecture: $arch" >&2; exit 1 ;; esac \
    && curl -fsSL --retry 3 -o /tmp/zig.tar.xz \
         "https://ziglang.org/download/${ZIG_VERSION}/zig-${zarch}-linux-${ZIG_VERSION}.tar.xz" \
    && echo "$sha  /tmp/zig.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/zig && tar -xJf /tmp/zig.tar.xz -C /opt/zig --strip-components=1 \
    && rm /tmp/zig.tar.xz && /opt/zig/zig version \
    && echo "$zarch" > /tmp/zig-arch
WORKDIR /src
COPY agent/ ./
RUN /opt/zig/zig build -Doptimize=ReleaseSafe -Dtarget="$(cat /tmp/zig-arch)-linux" -j4 \
    && zig-out/bin/fx --version

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/fx/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /src/zig-out/bin/fx /opt/fx/bin/fx
RUN /opt/fx/bin/fx --version \
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

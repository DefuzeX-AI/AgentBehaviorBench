# Build the selected upstream commit from source the way its release workflow
# builds the Linux binary: the Zig release named by the commit's build.zig.zon
# `minimum_zig_version` (the version its release workflow pins), then
# `zig build -Doptimize=ReleaseSafe -Dtarget=<arch>-linux`. `zig build` fetches
# whatever build.zig.zon declares at build time.
FROM debian:bookworm-slim AS build
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*
ENV ZIG_GLOBAL_CACHE_DIR=/tmp/zig-global ZIG_LOCAL_CACHE_DIR=/tmp/zig-local
COPY agent/build.zig.zon /tmp/build.zig.zon
# Official tarball sha256 values from https://ziglang.org/download/index.json.
RUN version=$(sed -n 's/^[[:space:]]*\.minimum_zig_version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' /tmp/build.zig.zon) \
    && arch="${TARGETARCH:-$(uname -m)}" \
    && case "$arch" in amd64|x86_64) zarch=x86_64 ;; arm64|aarch64) zarch=aarch64 ;; \
         *) echo "unsupported architecture: $arch" >&2; exit 1 ;; esac \
    && case "$version/$zarch" in \
         0.16.0/x86_64)  sha=70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00 ;; \
         0.16.0/aarch64) sha=ea4b09bfb22ec6f6c6ceac57ab63efb6b46e17ab08d21f69f3a48b38e1534f17 ;; \
         0.17.0/x86_64)  sha=1cbe9df9f27e6b78d14ccbca43b6703a404ef79ef1c463de901d7f088d4e2026 ;; \
         0.17.0/aarch64) sha=9e8d11661d4ae3bd57702a3832781e23ad151dde5798e16a5ccd503f65234ff8 ;; \
         *) echo "no pinned Zig toolchain for minimum_zig_version '${version}' on ${zarch}; add its sha256 to this table" >&2; exit 1 ;; esac \
    && curl -fsSL --retry 3 -o /tmp/zig.tar.xz \
         "https://ziglang.org/download/${version}/zig-${zarch}-linux-${version}.tar.xz" \
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

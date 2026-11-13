# Build the selected upstream commit from source the way its release workflow
# builds the Linux binary: Alpine/musl + clang 22, CMake + Ninja, fully static
# Release. The exported tree must include the commit-pinned third_party/
# submodules; nlohmann_json and simdjson come from the tags pinned in its CMake.
FROM alpine:3.24 AS build
ARG TARGETARCH
RUN apk add --no-cache build-base clang22 clang22-static lld22 llvm22 \
        cmake samurai git linux-headers pkgconf \
        openssl-dev openssl-libs-static nghttp2-dev nghttp2-static zlib-static
WORKDIR /src
COPY agent/ ./
RUN for m in acp-cpp claybin jsonrpc-cpp maya maya/third_party/jaal mcp-cpp rag-cpp richpaste; do \
        [ -n "$(ls -A "third_party/$m" 2>/dev/null)" ] \
        || { echo "third_party/$m is empty: the source must include its submodules" >&2; exit 1; }; \
    done \
    && arch="${TARGETARCH:-$(uname -m)}" \
    && case "$arch" in amd64|x86_64) cmarch=sse2 ;; arm64|aarch64) cmarch=native ;; \
         *) echo "unsupported architecture: $arch" >&2; exit 1 ;; esac \
    && cmake -S . -B build-rel -GNinja -DCMAKE_BUILD_TYPE=Release \
         -DCMAKE_C_COMPILER=clang-22 -DCMAKE_CXX_COMPILER=clang++-22 \
         -DAGENTTY_STANDALONE=ON -DAGENTTY_FULLY_STATIC=ON \
         -DAGENTTY_AUTO_PULL_MAYA=OFF -DAGENTTY_USE_MIMALLOC=OFF \
         -DAGENTTY_COMPILER_CACHE=OFF -DAGENTTY_ARCH="$cmarch" \
    && cmake --build build-rel --target agentty -j4 \
    && strip build-rel/agentty \
    && if readelf -d build-rel/agentty 2>/dev/null | grep -q NEEDED; then \
         echo "agentty is not statically linked" >&2; exit 1; fi \
    && build-rel/agentty --version

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/opt/agentty/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /src/build-rel/agentty /opt/agentty/bin/agentty
RUN /opt/agentty/bin/agentty --version \
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

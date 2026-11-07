# Build both Go binaries from the restored source (source.method = "git" restores the pinned
# commit into agent/): the OCR CLI from the root module and the ocr-acp adapter from acp/.
# The root go.mod declares go 1.26.9; one pinned toolchain compiles both modules.
FROM golang:1.26.9-trixie AS builder
ENV GOTOOLCHAIN=local
WORKDIR /src
COPY agent/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/opencodereview ./cmd/opencodereview \
    && cd acp \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/ocr-acp ./cmd/ocr-acp

# Runtime: Debian trixie ships Git >= 2.41 (OCR README prerequisite; bookworm has 2.39).
FROM python:3.12-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent

COPY --from=builder /out/opencodereview /opt/agent/bin/opencodereview
COPY --from=builder /out/ocr-acp /opt/agent/bin/ocr-acp
RUN ln -s /opt/agent/bin/opencodereview /opt/agent/bin/ocr \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/

ENV PATH="/opt/agent/bin:$PATH" \
    PYTHONPATH="/opt/abb-runtime" \
    PYTHONUNBUFFERED=1 \
    HOME="/home/agent"

USER agent

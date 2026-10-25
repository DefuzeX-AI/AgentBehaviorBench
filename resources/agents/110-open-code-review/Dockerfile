# Stage 1: Build Go binaries
FROM golang:1.26-bookworm AS builder

WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

# Clone pinned commit of alibaba/open-code-review
RUN git clone https://github.com/alibaba/open-code-review.git . \
    && git checkout 375f64cd6f67a48a135da83cfcf59c52669a09cb

# Build opencodereview CLI
RUN go build -trimpath -ldflags="-s -w" -o /out/opencodereview ./cmd/opencodereview

# Build ocr-acp adapter
RUN cd acp && go build -trimpath -ldflags="-s -w" -o /out/ocr-acp ./cmd/ocr-acp

# Stage 2: Runtime image
FROM python:3.11-slim-bookworm

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ripgrep \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent

# Install ABB runtime, adapter, and SDK dependencies
RUN pip install --no-cache-dir \
    --index-url "$ABB_PIP_INDEX_URL" \
    --timeout 120 --retries 5 \
    'opentelemetry-sdk>=1.30,<2' \
    'jsonschema>=4.23,<5' \
    'python-dotenv>=1,<2' \
    'agent-client-protocol==0.12.1' \
    'filelock>=3.32.7,<4' \
    'PyYAML>=6,<7' \
    'kuma-defuzex[otel]>=0.3.3'

# Install binaries from builder stage
COPY --from=builder /out/opencodereview /opt/agent/bin/opencodereview
COPY --from=builder /out/ocr-acp /opt/agent/bin/ocr-acp
RUN ln -s /opt/agent/bin/opencodereview /opt/agent/bin/ocr

# Create non-root agent user (UID 10001) and workspace
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent /opt/agent

# Copy ABB unit glue assets
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
RUN cp bootstrap/sitecustomize.py /usr/local/lib/python3.11/site-packages/sitecustomize.py \
    && git config --system --add safe.directory "*"

ENV PATH="/opt/agent/bin:$PATH" \
    PYTHONPATH="/opt/abb-runtime:/opt/agent:/opt/agent/bootstrap" \
    PYTHONUNBUFFERED=1 \
    HOME="/home/agent"

USER agent

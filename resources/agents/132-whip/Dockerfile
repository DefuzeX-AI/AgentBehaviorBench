FROM golang:1.27.2-bookworm AS build
WORKDIR /src
COPY agent/go.mod agent/go.sum ./
RUN go mod download
COPY agent/ ./
# Upstream explicitly supports a plain Go development build without web assets.
# This unit invokes the native ACP/daemon runtime; no web listener is started.
RUN CGO_ENABLED=0 go build -trimpath -ldflags '-X main.version=abb-1c5da05987d2' -o /out/whipcode ./cmd/whip

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates bash git ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY --from=build /out/whipcode /usr/local/bin/whipcode
ENV PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent SHELL=/bin/bash
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

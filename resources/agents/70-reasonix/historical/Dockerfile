# Build the requested upstream commit the way its .goreleaser.yaml does
# (CGO_ENABLED=0, -trimpath, ./cmd/reasonix), then lay it out exactly like the
# release install: /opt/reasonix/bin/reasonix in a node:24-bookworm runtime.
FROM golang:1.26-bookworm AS build
# go.mod pins `toolchain go1.2x.y`; let the go command fetch it when newer.
ENV GOTOOLCHAIN=auto CGO_ENABLED=0 GOFLAGS=-mod=readonly
WORKDIR /src
COPY agent/go.mod agent/go.sum ./
RUN go mod download
COPY agent/ ./
COPY provenance.json /tmp/provenance.json
RUN commit=$(sed -n 's/.*"resolved_revision": *"\([0-9a-f]*\)".*/\1/p' /tmp/provenance.json) \
    && go build -trimpath -ldflags "-s -w -X main.gitCommit=${commit%"${commit#????????????}"}" \
        -o /out/reasonix ./cmd/reasonix \
    && /out/reasonix --version

FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/reasonix/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY --from=build /out/reasonix /opt/reasonix/libexec/reasonix
COPY historical/reasonix-shim.sh /opt/reasonix/bin/reasonix
COPY historical/acp-stop-reason.py /opt/reasonix/libexec/acp-stop-reason.py
# bootstrap/launch.py passes the newest `reasonix acp` flag set; older commits
# define only a subset (e.g. no --permission-mode before v2.x, no --profile in
# v1.31-v1.38), and the acp flag parser rejects unknown flags. Record the flags
# this build defines so the shim drops only the ones it does not.
RUN chmod 0755 /opt/reasonix/bin/reasonix /opt/reasonix/libexec/reasonix \
    && (/opt/reasonix/libexec/reasonix acp --help 2>&1 || true) \
        | grep -oE '^ +--?[a-z][a-z0-9-]*' | sed 's/^ *-*//' | sort -u > /opt/reasonix/libexec/acp-flags \
    && grep -qx workspace-only /opt/reasonix/libexec/acp-flags \
    && echo "acp flags: $(tr '\n' ' ' < /opt/reasonix/libexec/acp-flags)" \
    && /opt/reasonix/bin/reasonix --version \
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

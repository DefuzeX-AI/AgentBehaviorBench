# Build the selected upstream commit from its own go.mod/go.sum, as its release does:
# goreleaser builds ./cmd/reasonix (binary `reasonix`) with CGO_ENABLED=0 and -trimpath,
# using the go.mod toolchain (setup-go go-version-file). The repository root has no
# main package; cmd/reasonix-launcher is not part of the CLI archive.
FROM golang:1.26-bookworm AS build
ENV CGO_ENABLED=0 GOFLAGS=-mod=readonly GOPATH=/go
WORKDIR /src
COPY agent/ ./
COPY provenance.json /tmp/provenance.json
RUN toolchain=$(sed -n 's/^toolchain //p' go.mod) \
    && export GOTOOLCHAIN=${toolchain:-local} \
    && rev=$(sed -nE 's/.*"(resolved|base)_revision": *"([0-9a-f]{40})".*/\2/p' /tmp/provenance.json | head -n1) \
    && test -n "$rev" && short=$(printf %s "$rev" | cut -c1-9) \
    && go mod download \
    && go build -p 4 -trimpath -o /out/reasonix -ldflags "-s -w -X main.gitCommit=$short \
       -X reasonix/internal/productdocs.linkedRevision=$rev -X reasonix/internal/tools/productdocs.linkedRevision=$rev" \
       ./cmd/reasonix \
    && go version /out/reasonix

FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/reasonix/bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY --from=build /out/reasonix /opt/reasonix/libexec/reasonix
COPY historical/acp-compat.sh /tmp/acp-compat.sh
# bootstrap/launch.py execs /opt/reasonix/bin/reasonix. Install the built binary there
# directly; only when this revision's `acp` lacks one of the launcher's flags, put the
# flag-dropping shim in front of it.
RUN mkdir -p /opt/reasonix/bin && probe=$(mktemp -d) \
    && help=$(HOME=$probe REASONIX_HOME=$probe /opt/reasonix/libexec/reasonix acp -h 2>&1) \
    && rm -rf "$probe" && unsupported= \
    && for flag in profile permission-mode sandbox-bash workspace-only; do \
         printf '%s\n' "$help" | grep -Eq -- "^ +--?$flag( |\$)" || unsupported="$unsupported $flag"; done \
    && if [ -z "$unsupported" ]; then mv /opt/reasonix/libexec/reasonix /opt/reasonix/bin/reasonix; \
       else sed "s/@UNSUPPORTED@/${unsupported# }/" /tmp/acp-compat.sh > /opt/reasonix/bin/reasonix \
            && chmod 0755 /opt/reasonix/bin/reasonix && echo "acp compat shim for:$unsupported"; fi \
    && rm /tmp/acp-compat.sh && /opt/reasonix/bin/reasonix --version \
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

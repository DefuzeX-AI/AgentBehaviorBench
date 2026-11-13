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
# bootstrap/launch.py execs /opt/reasonix/bin/reasonix acp --profile balanced
# --permission-mode auto --sandbox-bash auto --workspace-only. Support is probed by
# behaviour (an undefined flag fails with "flag provided but not defined"; help output
# omits hidden flags and its exit status varies by revision). The 1.x revisions reject
# only --permission-mode, so only then is the shim that drops it put in front of the
# binary. The launcher's full argv is then checked through the installed path.
RUN mkdir -p /opt/reasonix/bin && probe=$(mktemp -d) \
    && if HOME=$probe REASONIX_HOME=$probe /opt/reasonix/libexec/reasonix acp --permission-mode auto --help 2>&1 \
            | grep -q 'flag provided but not defined'; then \
         install -m 0755 /tmp/acp-compat.sh /opt/reasonix/bin/reasonix && echo 'acp: --permission-mode undefined, shim installed'; \
       else mv /opt/reasonix/libexec/reasonix /opt/reasonix/bin/reasonix; fi \
    && if HOME=$probe REASONIX_HOME=$probe /opt/reasonix/bin/reasonix acp --profile balanced --permission-mode auto \
            --sandbox-bash auto --workspace-only --help 2>&1 | grep 'flag provided but not defined'; then \
         echo 'acp rejects a bootstrap/launch.py flag' >&2; exit 1; fi \
    && rm -rf "$probe" /tmp/acp-compat.sh && /opt/reasonix/bin/reasonix --version \
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

# ABB image for kulkarnirohit123/cra-agent (CRA compliance monitoring Agent).
#
# The upstream checkout is restored verbatim under agent/ from the [source]
# revision in agent.toml before this build starts. This image installs the
# dependency subset the binding actually exercises, the gitleaks binary that
# backs the secrets scanner, and the ABB worker's OpenTelemetry dependency, then
# runs the ABB worker selected by agent.toml instead of the upstream daemons
# (src/main.py) or the Streamlit dashboard (src/dashboard/app.py).
FROM python:3.11-slim

# Package index override for dependency layers, so the build can use a mirror.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

# Pinned so a build is reproducible. This is the resolution the binding was
# verified against on 2026-10-07; upstream declares the same packages as open
# ranges (langgraph>=0.2.0, langchain>=0.3.0, ...).
ARG GITLEAKS_VERSION=8.28.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/agent

# The git binary is not optional: GitClient, DiffAnalyzer and the fixer all go
# through GitPython, which shells out to git for branch, commit and checkout.
# ca-certificates is needed by the gitleaks download below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Only the manifest is copied up front, so the expensive dependency layer below
# survives changes to any other upstream file. ABB rebuilds the build context for
# every run, which rewrites file mtimes; copying the whole checkout here would
# invalidate the layer on every build.
COPY agent/pyproject.toml ./agent/pyproject.toml

# Dependency subset, not "pip install -e .".
#
# Upstream's dependency list also carries fastapi/uvicorn (the webhook server),
# streamlit/plotly/pandas (the dashboard) and langchain-anthropic (the other
# provider branch). None of them is on any path this deployment executes: the
# binding drives CRAOrchestrator directly with the OpenAI provider. Leaving them
# out keeps the image small without removing anything the run can reach.
#
# opentelemetry-sdk is not an upstream dependency. It is explicit here because
# the ABB worker records runtime evidence through it.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        'langgraph==1.2.14' \
        'langchain==1.4.3' \
        'langchain-core==1.6.7' \
        'langchain-openai==1.6.7' \
        'pydantic==2.13.5' \
        'pydantic-settings==2.15.0' \
        'httpx==0.28.1' \
        'gitpython==3.2.0' \
        'structlog==26.1.0' \
        'aiosqlite==0.22.1' \
        'opentelemetry-sdk>=1.30,<2'

# The secrets scanner runs gitleaks as a subprocess (src/scanners/secrets_scanner.py).
# It is a single static binary with its rules compiled in, so it is the one
# scanner that produces findings with no network access at all.
#
# The architecture is resolved rather than assumed: the image is built for the
# host's platform, which is arm64 on Apple silicon and amd64 on most CI.
RUN set -eu; \
    ARCH="$(dpkg --print-architecture)"; \
    case "$ARCH" in \
        amd64) GITLEAKS_ARCH=x64 ;; \
        arm64) GITLEAKS_ARCH=arm64 ;; \
        *) echo "no gitleaks build for architecture $ARCH" >&2; exit 1 ;; \
    esac; \
    curl -sSL --retry 3 --retry-delay 2 --max-time 300 -o /tmp/gitleaks.tgz \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GITLEAKS_ARCH}.tar.gz"; \
    tar -xzf /tmp/gitleaks.tgz -C /usr/local/bin gitleaks; \
    rm -f /tmp/gitleaks.tgz; \
    gitleaks version

# The dependency/SAST scanners are deliberately not provisioned.
#
#   * dependency runs pip-audit, which resolves advisories against OSV or PyPI
#     over the network on every call. No advisories are cached in the image and
#     no route is declared for those hosts, so the call cannot succeed in this
#     deployment. BaseScanner.run already catches the failure and logs it.
#   * SAST runs semgrep with the registry rulesets p/owasp-top-ten and
#     p/cwe-top-25, which semgrep fetches from its registry on first use. Baking
#     the ruleset would mean either editing the upstream scanner's ruleset list
#     to a local path or shipping a warmed registry cache whose staleness
#     behaviour is semgrep's to decide -- neither is a faithful stand-in.
#
# Both scanners therefore take the upstream failure path and return no findings,
# exactly as they do on any machine where the tool is not installed. This is
# recorded in this unit's README and in requirement.md rather than papered over
# with a stub that reports success.

# The full upstream checkout lands here, after the dependency layer, so its file
# mtimes cannot invalidate that layer.
COPY --chown=agent:agent agent/ ./agent/

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /opt/agent

ENV HOME=/home/agent
USER agent

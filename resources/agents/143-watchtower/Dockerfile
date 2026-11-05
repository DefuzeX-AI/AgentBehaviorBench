# Outer ABB image for Watchtower. Build context is the outer Agent unit (`.`),
# not the upstream `agent/` checkout. Watchtower is loose source with only a
# requirements.txt (no installable package metadata), so dependencies are
# installed and the `watchtower/` package is imported from source.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# System security-tool dependencies, matching the upstream agent/Dockerfile.
# The worker shells out to these binaries (watchtower/tools/* wrappers).
RUN apt-get update && apt-get install -y \
    nmap \
    masscan \
    curl \
    wget \
    git \
    make \
    dnsutils \
    unzip \
    ruby \
    ruby-dev \
    build-essential \
    libpcap-dev \
    golang \
    nodejs \
    npm \
    whatweb \
    && rm -rf /var/lib/apt/lists/*

ENV GOPATH=/go \
    PATH=/usr/local/go/bin:/go/bin:$PATH

# Go-based recon tools, installed best-effort. Each tool is independent so a
# single upstream packaging breakage does not abort the image build: upstream
# pins kiterunner to a non-existent `cmd/kr` path. Amass is installed from a
# checksum-verified release below instead of the broken upstream Go pin. A tool
# that fails to install is simply unavailable at runtime and degrades to an error
# observation, per requirement.md Known Limitations.
RUN set -u; \
    for mod in \
        github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest \
        github.com/projectdiscovery/httpx/cmd/httpx@latest \
        github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest \
        github.com/ffuf/ffuf/v2@latest \
        github.com/OJ/gobuster/v3@latest \
    ; do go install -v "$mod" || echo "WARN: go install $mod failed; tool unavailable"; done; \
    ( go install -v github.com/assetnote/kiterunner@latest && ln -sf /go/bin/kiterunner /usr/local/bin/kiterunner ) || echo "WARN: kiterunner unavailable"

# Ruby-based tools (best-effort; a gem build failure does not abort the image).
RUN gem install wpscan || echo "WARN: wpscan gem install failed; tool unavailable"

# Python-based security CLI tools. Upstream also pip-installs dalfox, gitleaks,
# cmseek and retire, but those are Go/npm/GitHub tools with no PyPI distribution
# (pip 404), so that upstream layer fails to build. They are omitted here; the
# agent treats the missing binaries as unavailable tools (error observation), as
# documented in requirement.md Known Limitations.
RUN python -m pip install --no-cache-dir \
    sqlmap wafw00f arjun xsstrike sslyze \
    || echo "WARN: one or more python security CLI tools failed to install; unavailable"

# Nikto and testssl.sh from source (best-effort git clones).
RUN ( git clone --depth 1 https://github.com/sullo/nikto.git /opt/nikto \
    && ln -sf /opt/nikto/program/nikto.pl /usr/local/bin/nikto ) || echo "WARN: nikto unavailable"

RUN ( git clone --depth 1 https://github.com/drwetter/testssl.sh.git /opt/testssl \
    && ln -sf /opt/testssl/testssl.sh /usr/local/bin/testssl ) || echo "WARN: testssl unavailable"

# Install Python dependencies from the upstream requirements.txt. The project
# itself is NOT pip-installed; /opt/agent/agent on PYTHONPATH exposes it.
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent

# Copy the complete upstream source (graph factory, nodes, tools, assets).
COPY agent/ ./agent/

# Writable workspace owned by the non-root user (private SQLite MemoryStore).
RUN mkdir -p /opt/agent/workspace && chown -R agent:agent /opt/agent

ENV HOME=/home/agent

# BBA runtime modules and saved outer binding beside agent.toml.
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Watchtower invokes the v3 `enum -passive` CLI. Pin the compatible official
# release and fail the build on download, checksum, or installation errors.
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      arm64) amass_arch=arm64; amass_sha=b67dfdf5659268bb48626ef39bf9c2c74c0b5d34d21c232a17e07ba200be11b5 ;; \
      amd64) amass_arch=amd64; amass_sha=2b5afb8a567d9703dfb416099fb0452e2b4b4da5170f0b23cd3b812df2e9319c ;; \
      *) echo "Unsupported Amass architecture" >&2; exit 1 ;; \
    esac; \
    curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 \
      "https://github.com/owasp-amass/amass/releases/download/v3.23.3/amass_Linux_${amass_arch}.zip" \
      --output /tmp/amass.zip; \
    echo "${amass_sha}  /tmp/amass.zip" | sha256sum --check -; \
    unzip -q /tmp/amass.zip -d /tmp/amass-release; \
    install -m 0755 "/tmp/amass-release/amass_Linux_${amass_arch}/amass" /usr/local/bin/amass; \
    amass -version; \
    rm -rf /tmp/amass.zip /tmp/amass-release

# Preload the official template release for the non-root runtime user. Avoid
# depending on the first scan downloading its data through restricted egress.
RUN set -eu; \
    git init -q /home/agent/nuclei-templates; \
    git -C /home/agent/nuclei-templates remote add origin https://github.com/projectdiscovery/nuclei-templates.git; \
    git -C /home/agent/nuclei-templates fetch --depth 1 origin f8b8b8dcd70d93826c3767e1829ef8243af9f03b; \
    git -C /home/agent/nuclei-templates checkout -q --detach FETCH_HEAD; \
    test "$(git -C /home/agent/nuclei-templates rev-parse HEAD)" = f8b8b8dcd70d93826c3767e1829ef8243af9f03b; \
    rm -rf /home/agent/nuclei-templates/.git; \
    chown -R agent:agent /home/agent/nuclei-templates

# Native gobuster/ffuf wrappers read wordlist.txt from /opt/agent.
RUN set -eu; \
    curl -fsSL --retry 3 --max-time 120 \
      https://raw.githubusercontent.com/danielmiessler/SecLists/75064ac792b5b554d17386abae3f0e38db7f923c/Discovery/Web-Content/common.txt \
      -o /opt/agent/wordlist.txt; \
    echo "47fb86ca6fb3f97e5491161581900d6d99851fb16764eacddf16aa85617c956a  /opt/agent/wordlist.txt" | sha256sum --check -; \
    curl -fsSL --retry 3 --max-time 120 \
      https://raw.githubusercontent.com/danielmiessler/SecLists/75064ac792b5b554d17386abae3f0e38db7f923c/LICENSE \
      -o /opt/agent/wordlist.LICENSE; \
    chmod 0644 /opt/agent/wordlist.txt /opt/agent/wordlist.LICENSE; \
    ln -s /opt/testssl/testssl.sh /usr/local/bin/testssl.sh

USER agent

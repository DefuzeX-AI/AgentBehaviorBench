# Install the pinned Hermes Agent tag from source with upstream's own frozen uv.lock
# (the project deliberately refuses wheel/sdist builds; upstream's Docker image and
# dev setup both use `uv sync` + an editable project install). ACP adapter = [acp] extra.
FROM python:3.13-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/* && python -m venv /opt/venv && python -m venv /opt/uv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN set -eu; \
    /opt/uv/bin/python -m pip install --no-cache-dir --require-hashes -r agent/build-requirements.txt; \
    field() { python -c "import json,sys;print(json.load(open('agent/distribution.json'))[sys.argv[1]])" "$1"; }; \
    git clone --depth 1 --branch "$(field tag)" "$(field repository)" /opt/hermes; \
    test "$(git -C /opt/hermes rev-parse HEAD)" = "$(field commit)"; \
    rm -rf /opt/hermes/.git; \
    cd /opt/hermes && UV_PYTHON=/usr/local/bin/python3.13 UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 \
        /opt/uv/bin/uv sync --frozen --no-dev --extra acp; \
    /opt/hermes/.venv/bin/python -m ensurepip --default-pip; \
    rm -rf /opt/uv; \
    url="$(python -c "import json;print(json.load(open('/opt/agent/agent/tirith.json'))['url'])")"; \
    sum="$(python -c "import json;print(json.load(open('/opt/agent/agent/tirith.json'))['sha256'])")"; \
    curl -fsSL --retry 3 -o /tmp/tirith.tgz "$url"; \
    echo "$sum  /tmp/tirith.tgz" | sha256sum -c -; \
    mkdir -p /opt/tirith/bin; tar -xzf /tmp/tirith.tgz -C /opt/tirith/bin tirith; rm /tmp/tirith.tgz; \
    TIRITH_OFFLINE=1 /opt/tirith/bin/tirith --version; \
    /opt/hermes/.venv/bin/hermes --version; \
    python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'; \
    useradd --create-home --uid 10001 agent; \
    mkdir -p /home/agent/workspace; \
    chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

# Headless Chromium for the browser tool. abb-chromium imports the interceptor CA into
# Chromium's NSS store before launch; zz-abb-lean keeps Chromium within the container's
# pid budget (#158).
USER root
RUN apt-get update && apt-get install -y --no-install-recommends chromium libnss3-tools fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY abb-chromium /usr/local/bin/abb-chromium
RUN chmod 755 /usr/local/bin/abb-chromium
COPY zz-abb-lean /etc/chromium.d/zz-abb-lean
USER agent

# agent-browser 0.26.0 native CLI (the version Hermes pins, tools/browser_tool.py:124),
# sha256-pinned; it attaches to the Chromium launch.py starts (BROWSER_CDP_URL).
USER root
RUN set -eu; \
    case "$(dpkg --print-architecture)" in amd64) b=linux-x64;; arm64) b=linux-arm64;; *) echo unsupported arch >&2; exit 1;; esac; \
    curl -fsSL --retry 3 -o /tmp/agent-browser.tgz https://registry.npmjs.org/agent-browser/-/agent-browser-0.26.0.tgz; \
    echo "8a48cf4110d7dc2c12c1c4d6d25e0babdfa31604b537f05df0dc835fe2f854bf  /tmp/agent-browser.tgz" | sha256sum -c -; \
    tar -xzf /tmp/agent-browser.tgz -C /tmp "package/bin/agent-browser-$b"; \
    install -m 755 "/tmp/package/bin/agent-browser-$b" /usr/local/bin/agent-browser; \
    rm -rf /tmp/agent-browser.tgz /tmp/package; agent-browser --version
USER agent

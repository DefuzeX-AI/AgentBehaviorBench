# Install the pinned Octop release (hash-locked PyPI closure) into its own venv;
# its inbound ACP server (`octop acp`) is part of the release, so no dashboard
# build or Node stage is needed. Octop requires Python >= 3.12.
FROM python:3.12-bookworm
# git and ripgrep are present because Octop's shell/file tooling expects them on
# PATH; build-essential is needed because the dependency closure contains one sdist
# (crcmod) whose optional C extension is compiled during install. Nothing in ACP
# mode fetches packages at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git curl ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv && python -m venv /opt/octop
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent \
    OCTOP_HOME=/home/agent/.octop \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN /opt/octop/bin/pip install --no-cache-dir --require-hashes --no-deps -r agent/requirements.txt \
    && /opt/octop/bin/octop --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

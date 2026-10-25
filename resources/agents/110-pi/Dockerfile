# Install the pinned signed Pi release binary; `pi --acp` is the upstream ACP
# server, so no Rust toolchain is needed in the image.
FROM python:3.12-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
ARG PI_VERSION=0.8.0
# sha256 taken from the release's own pi-linux-amd64.tar.xz.sha256 asset.
ARG PI_SHA256=c04e7f87391becb17cb1ec7544d0fd767231dfb5a8361644ea8870ba3d39056d
RUN curl -fsSL -o /tmp/pi.tar.xz \
      "https://github.com/Dicklesworthstone/pi_agent_rust/releases/download/v${PI_VERSION}/pi-linux-amd64.tar.xz" \
    && echo "${PI_SHA256}  /tmp/pi.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/pi.tar.xz -C /usr/local/bin pi \
    && rm /tmp/pi.tar.xz \
    && chmod 0755 /usr/local/bin/pi \
    && pi --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
WORKDIR /opt/agent
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

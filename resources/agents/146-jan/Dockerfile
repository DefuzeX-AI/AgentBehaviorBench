FROM debian:bookworm-slim

# Install system dependencies: Rust, Cargo, Node (needed for native build), Python for ABB worker.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates build-essential pkg-config libssl-dev \
       python3 python3-pip python3-venv \
       nodejs npm git \
       openssl \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && ln -s /root/.cargo/bin/cargo /usr/local/bin/cargo \
    && ln -s /root/.cargo/bin/rustc /usr/local/bin/rustc \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

WORKDIR /opt/agent

# Copy the entire source tree for build; Jan CLI expects all workspace crates.
COPY agent/ ./agent/

# Build the upstream headless CLI, excluding desktop-only Tauri modules.
RUN cd agent/src-tauri/jan-cli && cargo build --release --no-default-features --features cli && \
    mkdir -p /usr/local/bin && \
    cp ../target/release/jan /usr/local/bin/jan

# Provide the Python executable/pip expected by ABB overlays without modifying
# Debian's externally managed system Python installation.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RUN python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'
ENV HOME=/home/agent

# Create agent user and workspace
RUN useradd --create-home --uid 10001 agent && \
    mkdir -p /workspace && \
    chown agent:agent /workspace

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml
COPY bootstrap/ ./bootstrap/

USER agent
WORKDIR /opt/agent

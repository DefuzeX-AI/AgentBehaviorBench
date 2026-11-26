# Base image with Python for the BBA worker.
FROM python:3.11-slim

# Install Node.js >=20, as required by the agent's package.json.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set up environment for the BBA Python worker.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

WORKDIR /opt/agent

# Copy agent source code.
COPY agent/ ./agent/

# Install Node.js dependencies and build the agent bundle.
# This creates the `bundle/gemini.js` executable.
WORKDIR /opt/agent/agent
RUN npm install && npm run build
WORKDIR /opt/agent

# Create a non-root user and the workspace required by the ACP adapter.
# Symlink the bundle into the workspace to align with the agent.toml command path.
# Keep installed code readable; only the runtime workspace needs write access.
RUN useradd --create-home --uid 10001 agent \
    && mkdir /workspace \
    && ln -s /opt/agent/agent/bundle /workspace/bundle \
    && chown agent:agent /opt/agent \
    && chown -h agent:agent /workspace/bundle \
    && chown agent:agent /workspace

# Copy BBA runtime components.
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

# Switch to the non-root user for runtime.
USER agent

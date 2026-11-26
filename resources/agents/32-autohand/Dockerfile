FROM node:24-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep ca-certificates \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && npm ci --omit=dev --no-audit --no-fund \
    && ./node_modules/.bin/autohand --version \
    && npm cache clean --force \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
# npm's install-script policy can defer these normal upstream lifecycle steps.
# Run the pinned packages' own scripts explicitly, without modifying their code.
RUN cd agent \
    && npm explore node-pty -- npm run install \
    && npm explore node-pty -- npm run postinstall \
    && npm explore node-llama-cpp -- npm run postinstall \
    && npm explore autohand-cli -- npm run postinstall \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
USER agent

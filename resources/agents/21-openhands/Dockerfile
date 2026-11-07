# Install the pinned OpenHands CLI release (PyPI `openhands`, hash-locked) into its own venv;
# its ACP server is built in (`openhands acp`).
FROM python:3.12-bookworm
ARG EXTENSIONS_REPO=https://github.com/OpenHands/extensions
ARG EXTENSIONS_COMMIT=f761809704f3edb2f25e737991277e1bb1ac3e88
RUN apt-get update && apt-get install -y --no-install-recommends tmux ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv && python -m venv /opt/openhands
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# OpenHands always syncs its public skills from GitHub at session start. Bake a local mirror at a
# pinned commit; launch.py redirects that URL here with git's insteadOf so no runtime egress occurs.
RUN /opt/openhands/bin/pip install --no-cache-dir --require-hashes --no-deps -r agent/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && git init --quiet --bare /opt/openhands-extensions.git \
    && git -C /opt/openhands-extensions.git fetch --quiet --depth 1 "$EXTENSIONS_REPO" "$EXTENSIONS_COMMIT" \
    && git -C /opt/openhands-extensions.git update-ref refs/heads/main "$EXTENSIONS_COMMIT" \
    && git -C /opt/openhands-extensions.git symbolic-ref HEAD refs/heads/main \
    && test "$(git -C /opt/openhands-extensions.git rev-parse main)" = "$EXTENSIONS_COMMIT" \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

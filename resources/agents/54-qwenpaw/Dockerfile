# Outer ABB image for QwenPaw (ACP over stdio). Launch behavior is owned by
# agent.toml: BBA runs `python -m agentbench.runtime.agentcontainer.worker`
# from /opt/agent, so no ENTRYPOINT/CMD is declared here.
# Build context is the outer Agent unit; agent/ is the pinned upstream checkout
# with install/abb-acp-launch.py applied into it as agent/abb-acp-launch.py.
FROM python:3.12-slim

# Toolchain for source dependencies with native extensions, and git for
# VCS-based dependencies; kept because the agent's own tools run shell commands.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /opt/agent
COPY agent/ ./agent/

# Install the pinned upstream checkout (setuptools package, src layout) into a
# dedicated venv so QwenPaw's dependency tree — including
# agent-client-protocol>=0.9,<0.11 used by its ACP server — stays isolated from
# the ABB worker interpreter. The venv deliberately stays OFF PATH: the BBA
# worker, the SDK overlay and the stdlib-only launcher all use the system
# `python`, and the launcher execs /opt/qwenpaw-venv/bin/qwenpaw by absolute
# path. "setuptools<82" follows the verified constraints for this revision.
RUN python -m venv /opt/qwenpaw-venv \
    && /opt/qwenpaw-venv/bin/pip install --no-cache-dir /opt/agent/agent "setuptools<82" \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/project \
    && chown -R agent:agent /workspace

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

# Writable HOME for the non-root agent user; /workspace is the adapter.cwd.
ENV HOME=/home/agent
USER agent

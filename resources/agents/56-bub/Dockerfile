# Outer ABB image for bub (bubbuild/bub) over ACP stdio via the bub-acp-server plugin
# (bubbuild/bub-contrib @ 8727b088, installed from Git at the pinned commit).
# BBA runs `python -m agentbench.runtime.agentcontainer.worker` from /opt/agent, which spawns
# `python /opt/agent/agent/abb-acp-launch.py` -> `/opt/bub-venv/bin/bub acp`.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent

WORKDIR /opt/agent

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY agent/ ./agent/

# Dedicated venv. Versions are constrained by bub-contrib's uv.lock at 8727b088 (exported to
# bub-constraints.txt; the lock pins bub at a93f5b80, the revision restored into agent/). The restored
# source has no .git, so hatch-vcs is given the lock's version string. The two bub-contrib plugins
# (bub-mcp, bub-acp-server) come from the pinned bub-contrib commit; only the package directories are
# copied out of the checkout, because the bub-contrib workspace root's [tool.uv.sources] points `bub`
# at git main, which would conflict with the restored revision.
ARG BUB_CONTRIB_REVISION=8727b088aea69615d44d3b58ab0b9be6d16a884e
RUN git init -q /tmp/bub-contrib \
    && git -C /tmp/bub-contrib fetch -q --depth 1 https://github.com/bubbuild/bub-contrib.git "$BUB_CONTRIB_REVISION" \
    && git -C /tmp/bub-contrib checkout -q FETCH_HEAD \
    && test "$(git -C /tmp/bub-contrib rev-parse HEAD)" = "$BUB_CONTRIB_REVISION" \
    && mkdir -p /opt/bub-contrib \
    && cp -r /tmp/bub-contrib/packages/bub-mcp /tmp/bub-contrib/packages/bub-acp-server /opt/bub-contrib/ \
    && rm -rf /tmp/bub-contrib
RUN python -m venv /opt/bub-venv \
    && /opt/bub-venv/bin/pip install --no-cache-dir uv \
    && SETUPTOOLS_SCM_PRETEND_VERSION=0.5.2.dev21+ga93f5b80c /opt/bub-venv/bin/uv pip install \
         --python /opt/bub-venv/bin/python --prerelease=allow --no-cache \
         -c /opt/agent/agent/bub-constraints.txt \
         '/opt/agent/agent[app]' \
         /opt/bub-contrib/bub-mcp \
         /opt/bub-contrib/bub-acp-server \
    && /opt/bub-venv/bin/bub acp --help >/dev/null

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/project \
    && chown -R agent:agent /workspace

USER agent

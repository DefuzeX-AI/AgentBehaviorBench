# Outer BBA Agent unit; COPY sources resolve from the outer build context.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PATH=/opt/agent/agent/backend/.venv/bin:$PATH \
    HOME=/home/agent \
    UV_PYTHON_DOWNLOADS=never

# Upstream deployment includes libgomp1 for the numerical dependency stack.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir uv

WORKDIR /opt/agent
# Preserve the descriptor, transitive imports, assets and repository README.
# The backend metadata hook reads ../README.md during package installation.
COPY agent/ ./agent/

WORKDIR /opt/agent/agent/backend
# Install the actual backend package and local_jupyter dependencies from uv.lock.
# The native build hook explicitly supports headless packaging via this flag.
# Frozen sync must fail rather than regenerate an incompatible lock.
RUN GIGA_AGENT_SKIP_UI_BUNDLE_CHECK=1 \
    uv sync --frozen --no-dev --extra jupyter --no-editable \
    && .venv/bin/python -m ensurepip --upgrade \
    && .venv/bin/python -m pip --version

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Native Jupyter processes use this same interpreter. Allow the final user to
# write runtime files and install packages into the shared virtual environment.
RUN useradd --create-home --user-group --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /opt/agent /home/agent

# The saved binding initializes CLI settings, SQLite and local Jupyter lazily.
# It disables secure execution explicitly; bubblewrap is not required.
# BBA launches the worker using agent.toml; do not start the upstream server.
USER agent

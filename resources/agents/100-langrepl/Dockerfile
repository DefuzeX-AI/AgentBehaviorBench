FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ripgrep fd-find tree bubblewrap ca-certificates \
    && ln -s /usr/bin/fdfind /usr/local/bin/fd \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install uv==0.8.2
ENV UV_HTTP_TIMEOUT=60 UV_CONCURRENT_DOWNLOADS=8 UV_CONCURRENT_BUILDS=2
WORKDIR /opt/agent/agent
COPY agent/pyproject.toml agent/uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/locked-requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --system --require-hashes -r /tmp/locked-requirements.txt
COPY agent/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv pip install --system --no-deps .
RUN python -m pip check

WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/langrepl \
    && chown -R agent:agent /workspace/langrepl
USER agent

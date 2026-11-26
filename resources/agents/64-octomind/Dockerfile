# Official release binaries correspond to the recorded source/tag and SHA256.
FROM python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash git ca-certificates curl ripgrep unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent
COPY bootstrap/ ./bootstrap/
RUN --mount=type=cache,id=abb-octomind-releases,target=/var/cache/abb-octomind-releases,sharing=locked \
    python bootstrap/install_releases.py
# Freeze the complete original tap, including capability definitions and symlinks.
# No native manifest, prompt, guard, skill or tool definition is rewritten.
RUN --mount=type=cache,id=abb-octomind-npm-downloads,target=/root/.npm,sharing=locked \
    git init /opt/octomind-tap \
    && git -C /opt/octomind-tap remote add origin https://github.com/Muvon/octomind-tap.git \
    && git -C /opt/octomind-tap fetch --depth 1 origin 27691ea9486151e2ceb522f2b610132ca77335f7 \
    && git -C /opt/octomind-tap checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/octomind-tap rev-parse HEAD)" = 27691ea9486151e2ceb522f2b610132ca77335f7 \
    && rm -rf /opt/octomind-tap/.git \
    && npm_config_prefer_offline=true npm_config_update_notifier=false npm install --global open-websearch@2.2.0 \
    && npm_config_prefer_offline=true npm_config_update_notifier=false npm exec --yes --package=open-websearch@2.2.0 -- node --version \
    && mkdir -p /opt/octomind-npm-cache \
    && cp -a /root/.npm/_cacache /opt/octomind-npm-cache/_cacache \
    && cp -a /root/.npm/_npx /opt/octomind-npm-cache/_npx \
    && python -m pip install --no-cache-dir --index-url "$PIP_INDEX_URL" \
       'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2'
RUN --mount=type=cache,id=abb-octomind-models,target=/var/cache/abb-octomind-models,sharing=locked \
    python bootstrap/prefetch_models.py
COPY agent/ ./agent/
COPY agent.toml ./
COPY network/ ./network/
COPY .abb-runtime/ /opt/abb-runtime/
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/project && chown -R agent:agent /workspace /home/agent
ENV PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 OCTOMIND_TELEMETRY=0 DO_NOT_TRACK=1
USER agent

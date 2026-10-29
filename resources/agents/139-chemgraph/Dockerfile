FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/src \
    HOME=/home/agent \
    CHEMGRAPH_LOG_DIR=/home/agent/workspace \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /opt/agent
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 agent
COPY agent/ ./agent/
# Install the upstream core unchanged. CPU PyTorch satisfies the upstream MACE
# requirement without bringing GPU-only CUDA libraries into this CPU image.
RUN python -m pip install --no-cache-dir 'uv==0.12.13' \
    && uv pip install --system --no-cache --no-deps \
        --index-url https://download.pytorch.org/whl/cpu 'torch==2.15.0+cpu' \
    && cp -R agent /tmp/chemgraph-src \
    && uv pip install --system --no-cache 'mace-torch==0.3.17' \
        'opentelemetry-sdk>=1.30,<2' /tmp/chemgraph-src \
    && uv pip check --system \
    && rm -rf /tmp/chemgraph-src

# Let the pinned MACE package resolve its own default MACE-MPA-0 checkpoint,
# then verify the official release asset before placing it in the user's cache.
# The native MaceCalc therefore keeps its default model without runtime network.
RUN python -c "from mace.calculators.foundations_models import download_mace_mp_checkpoint; print(download_mace_mp_checkpoint())" \
    && printf '%s  %s\n' \
        '75428afe3a1d7d8062e19bcaabd5c433623cabf308242ec9fb493e38604fb638' \
        '/home/agent/.cache/mace/macempa0mediummodel' | sha256sum -c - \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

FROM python:3.10-slim AS dependencies

# The pinned transformers dependency is installed from Git. OpenCV needs these
# shared libraries even when the requested input contains no image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates build-essential libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HOME=/home/agent

WORKDIR /opt/agent

RUN python -m pip install --no-cache-dir --upgrade pip

COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/temp /workspace/logs /model-weights \
    && chown -R agent:agent /workspace /model-weights

# Newer Diffusers imports Transformers APIs absent from the upstream pinned
# 4.46.0.dev0 commit. This version preserves native tool imports with that pin.
RUN python -m pip install --no-cache-dir 'diffusers==0.31.0' \
    && chown -R agent:agent /home/agent
ENV HF_HOME=/model-weights/huggingface \
    MPLCONFIGDIR=/workspace/.config/matplotlib

# Keep the large native dependency layer separate from ABB's runtime overlays.
FROM dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
RUN python -c "import medrax.tools"

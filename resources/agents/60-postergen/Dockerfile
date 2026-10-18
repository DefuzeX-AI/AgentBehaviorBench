# Outer ABB image for Y-Research-SBU/PosterGen onboarding
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    HF_HOME=/home/agent/.cache/huggingface

WORKDIR /opt/agent

# Install system dependencies:
# - git: needed for git-based dependencies (marker-pdf)
# - libreoffice: required by renderer.py to convert PPTX to PNG
# - libgl1, libglib2.0-0: required by opencv-python
# - fonts-dejavu-core: required for font rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libreoffice \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY agent/ ./agent/

# Install python dependencies and opentelemetry-sdk for ABB tracing
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r ./agent/requirements.txt 'rich>=13.0.0' 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /opt/agent/output /home/agent/.cache/huggingface \
    && chown -R agent:agent /opt/agent /home/agent \
    && python -c "from marker.models import create_model_dict; create_model_dict()" \
    && chown -R agent:agent /home/agent/.cache

RUN cp -r /root/.cache/datalab /home/agent/.cache/datalab \
    && python -c "from marker.util import download_font; download_font()" \
    && mkdir -p /usr/local/lib/python3.11/site-packages/static \
    && chown -R agent:agent /usr/local/lib/python3.11/site-packages/static \
    && chmod 755 /usr/local/lib/python3.11/site-packages/static \
    && ln -s /opt/agent/agent/config /opt/agent/config \
    && ln -s /opt/agent/agent/resource /opt/agent/resource \
    && ln -s /opt/agent/agent/fonts /opt/agent/fonts \
    && ln -s /opt/agent/agent/data /opt/agent/data \
    && chown -R agent:agent /home/agent/.cache /opt/agent
# Pre-install kuma-defuzex SDK to guarantee fast, offline-resilient evaluation builds
RUN python -m pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple 'kuma-defuzex[otel]>=0.3.3'

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

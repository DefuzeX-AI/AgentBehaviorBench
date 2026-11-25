FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent IN_DOCKER=true VIBESURF_WORKSPACE=/workspace
RUN apt-get update && apt-get install -y --no-install-recommends chromium build-essential git curl unzip fonts-noto-cjk libmagic1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/agent/agent
COPY agent/ ./
COPY constraints.txt /opt/vibesurf-constraints.txt
ENV PIP_CONSTRAINT=/opt/vibesurf-constraints.txt
RUN SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+abb pip install --no-cache-dir . \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-exporter-otlp-proto-http \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace && chown -R agent:agent /home/agent
USER agent
RUN python -c "from vibe_surf.browser.agen_browser_profile import AgentBrowserProfile; AgentBrowserProfile(executable_path='/usr/bin/chromium')._ensure_default_extensions_downloaded()"
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime:/opt/agent/agent
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

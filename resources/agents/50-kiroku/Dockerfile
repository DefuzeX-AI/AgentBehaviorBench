# Outer ABB image for Kiroku (requirements.txt + loose source, no installable package).
# Build context is the outer Agent unit; upstream source remains under agent/.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    HOME=/home/agent

WORKDIR /opt/agent

# Pandoc is required by Kiroku's document export path (README installation section);
# the binding may not exercise the UI save path, but answers confirm it is not disabled.
RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*

COPY agent/requirements.txt ./requirements.txt
# arxiv and wikipedia are optional langchain_community tool dependencies that
# the source imports directly (agents/tools.py) but does not pin.
# huggingface_hub is pinned below 0.26 because gradio==4.44.1 (imported by
# kiroku_app) still does `from huggingface_hub import HfFolder`, which was
# removed in huggingface_hub 0.26.
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'arxiv>=1.4,<3' 'wikipedia>=1.4,<2' 'huggingface_hub>=0.23,<0.26' \
    && useradd --create-home --shell /bin/bash --uid 10001 agent

COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# The runtime execution workdir is /opt/agent and the source may create project
# or temporary directories at runtime. Grant ownership to the final non-root user.
RUN mkdir -p /home/agent/.cache \
    && chown -R agent:agent /opt/agent /home/agent

USER agent

# ABB image for NVIDIA's Biomedical AI-Q Research Agent. The upstream source is
# preserved under agent/; this image installs its AIRA Python package and runs
# the ABB worker selected by agent.toml instead of the upstream FastAPI server.
FROM python:3.12-slim

# Keep the upstream dependency pins; select a reachable package index for this
# deployment. This build argument applies only to the native package layer.
ARG ABB_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_AIQ_AIRA=0.0.0 \
    MOLMIM_ENDPOINT_URL=https://health.api.nvidia.com/v1/biology/nvidia/molmim/generate \
    DIFFDOCK_ENDPOINT_URL=https://health.api.nvidia.com/v1/biology/mit/diffdock

WORKDIR /opt/agent
COPY agent/ ./agent/

# Python 3.12 and the package install match upstream's local-development and
# container setup. OTel is explicit because the ABB worker records runtime
# evidence in addition to the upstream package's Phoenix instrumentation.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
    --timeout 120 --retries 5 ./agent/aira 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /opt/agent/virtual_screening_output \
    && chown -R agent:agent /opt/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

ENV HOME=/home/agent
USER agent

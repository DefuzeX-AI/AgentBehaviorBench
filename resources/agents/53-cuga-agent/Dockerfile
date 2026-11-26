# Outer ABB image for CUGA (cuga-project/cuga-agent), pinned revision b219b48184c1544481e2568f2978ffb09fe8fbbb.
# Framework: ACP over stdio (adapter.command = python /opt/agent/agent/abb-acp-launch.py, cwd = /workspace/project).
# The BBA worker (launch.argv in agent.toml) is injected at run time; no ENTRYPOINT/CMD here.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PATH="/opt/cuga-venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/fastembed-cache \
    HF_HUB_OFFLINE=1 \
    ORT_DISABLE_TELEMETRY=1

WORKDIR /opt/agent

# CUGA pins torch/torchvision to the CPU index (pyproject.toml [tool.uv.sources] -> pytorch-cpu;
# uv.lock resolves torch 2.13.0+cpu from it). Seed the venv from that index so the package
# install cannot pull the CUDA wheel variants.
RUN python -m venv /opt/cuga-venv \
    && /opt/cuga-venv/bin/python -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu 'torch>=2.13.0'

# Installable package (pyproject.toml, src/ layout): install the pinned upstream checkout with
# the [acp] extra, which provides agent-client-protocol and the cuga-acp entrypoint used by
# the launcher. agent/ contains abb-acp-launch.py because the outer install/ inputs are
# applied into agent/ before the build; never edit the upstream source itself.
COPY agent/ ./agent/
RUN /opt/cuga-venv/bin/pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu '/opt/agent/agent[acp]' \
    && useradd --create-home --uid 10001 agent

# Pre-download the local fastembed embedding model (shortlister.embedding_model default
# BAAI/bge-small-en-v1.5 in src/cuga/config.py) so policy stores embed at startup without
# network access; FASTEMBED_CACHE_PATH is exported above for runtime cache reuse.
RUN HF_HUB_OFFLINE=0 /opt/cuga-venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed-cache')" \
    && chmod -R a+rX /opt/fastembed-cache

# BBA Python runtime modules and the saved manifest. No bindings/ directory: the adapter is
# ACP stdio, not an in-process graph.
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml

# adapter.cwd must exist and be writable by the runtime user (HOME comes from
# useradd --create-home; the launcher additionally sets a disposable HOME and CUGA_DBS_DIR
# per run and maps ABB_AGENT_MODEL_* to the native AGENT_SETTING_CONFIG/OPENAI_BASE_URL/
# OPENAI_API_KEY/MODEL_NAME variables — environment names only, never secrets in the image).
RUN mkdir -p /workspace/project \
    && chown -R agent:agent /workspace

USER agent

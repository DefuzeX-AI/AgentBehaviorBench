# ABB image for bamboo-moon/zhisaotong-Agent (Zhisaotong robot-vacuum support Agent).
#
# The upstream checkout is restored verbatim under agent/ from the [source] revision in
# agent.toml before this build starts. This image installs
# its declared requirements, the OpenAI-protocol model client the benchmark
# observes, the ABB worker's OpenTelemetry dependency and a CPU-only local ONNX
# embedder, then runs the ABB worker selected by agent.toml instead of the
# upstream Streamlit front end (app.py), which is only a UI layer over
# agent.react_agent.ReactAgent.
FROM python:3.12-slim

# Package index override for dependency layers, so the build can use a mirror.
#
# The default is Tencent Cloud rather than Aliyun on measured evidence: inside the
# Docker VM this container network resolves `mirrors.aliyun.com` to a host that
# serves ~47 KB/s, while `mirrors.cloud.tencent.com` serves ~6.3 MB/s from the same
# container -- a ~130x difference that turns a ~1 minute dependency install into a
# ~1.5 hour one. On the host both are fast, so the bottleneck is specific to how the
# container network reaches the Aliyun mirror. Override with
# `--build-arg ABB_PIP_INDEX_URL=https://pypi.org/simple/`.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

# Cache locations for the assets baked further down: the ONNX embedder behind
# rag_summarize, and the tiktoken ranks langchain-openai may need. Both cache
# variables must be set before the download and must stay readable by the
# runtime user.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    HF_ENDPOINT=https://hf-mirror.com \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    HF_HOME=/opt/fastembed-cache/hf \
    FASTEMBED_CACHE_PATH=/opt/fastembed-cache/models \
    ABB_RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

WORKDIR /opt/agent

# Only the requirements file is copied up front, so the expensive dependency layer
# below survives changes to any other upstream file.
#
# ABB rebuilds the build context from scratch for every run, which rewrites file
# mtimes. Copying the whole checkout here would therefore invalidate the dependency
# layer on every single build and re-download several hundred MB of wheels each time.
# The full checkout is copied afterwards, once the dependency layer is settled.
COPY agent/requirements.txt ./agent/requirements.txt

# Upstream's own pins are installed unchanged; the embedder and the OTel SDK are
# added for this deployment. OTel is explicit because the ABB worker records
# runtime evidence in addition to the upstream logging.
#
# Split from the model fetch below on purpose: the dependency layer is the slow
# one (langchain + chromadb + streamlit + onnxruntime) and stays cached across
# rebuilds of the much cheaper embedder layer.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        -r agent/requirements.txt 'opentelemetry-sdk>=1.30,<2' 'fastembed>=0.4,<1'

# Upstream pins the DashScope client only and never imports an OpenAI-protocol
# client, but this deployment needs one: ABB observes model traffic through its
# OpenAI-protocol interceptor, and upstream's ChatTongyi speaks DashScope's native
# protocol.
#
# The version is pinned to 1.1.10, the last release whose langchain-core floor
# (>=1.2.13) upstream's langchain-core==1.2.17 pin satisfies: 1.1.11 requires
# >=1.2.18 and 1.1.15 requires >=1.3.0, so an open range would silently upgrade
# langchain-core and change the Agent's pinned environment. langchain-core is
# restated here as a guard, so any future resolution that would move it fails the
# build instead of passing quietly.
#
# Kept as its own layer so the expensive dependency layer above stays cached.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        'langchain-openai==1.1.10' 'langchain-core==1.2.17'

# Upstream's own pins cannot resolve a working langgraph stack on their own, so the
# one broken edge is pinned here instead of editing agent/requirements.txt (the
# checkout under agent/ is preserved verbatim).
#
# langgraph==1.0.10 declares `langgraph-prebuilt>=1.0.8,<1.1.0`. That range is too
# wide: langgraph-prebuilt 1.0.9 and later import ExecutionInfo/ServerInfo from
# langgraph.runtime, which only langgraph>=1.1.0 provides. Because
# langchain==1.2.10 caps langgraph at <1.1.0, the upstream pin cannot move, and pip
# happily resolves the open range to langgraph-prebuilt 1.0.13 -- whereupon
# `from langchain.agents import create_agent`, the very first import in upstream's
# agent/agent/react_agent.py, dies with ImportError.
#
# Pinning langgraph-prebuilt to 1.0.8 -- the lower bound of that range, and the
# newest release whose imports langgraph 1.0.10 can actually satisfy -- restores the
# upstream stack without moving any other pin. langchain-core is restated as a guard
# for the same reason as the layer above.
#
# Verified in-image against langgraph 1.0.10: 1.0.8 imports cleanly and `pip check`
# reports no broken requirements.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        'langgraph-prebuilt==1.0.8' 'langchain-core==1.2.17'

# Declared here rather than in the block above so the slow dependency layer keeps
# its build cache: changing any earlier ENV or RUN invalidates every layer after it.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache

# Bake every runtime asset the Agent may need, so the finished image never reaches
# the network for anything except its declared model route.
#
#   * The ONNX embedder backs rag_summarize. Keeping it in-image is what makes the
#     RAG tool self-contained: no second hosted model, no extra credential and no
#     additional model route.
#   * The tiktoken ranks are cached because langchain-openai pulls tiktoken in and
#     tiktoken downloads its BPE tables from openaipublic.blob.core.windows.net on
#     first use. That host is not a declared route, so a lazy fetch at run time
#     would be denied by the egress policy. Both encodings are cached because the
#     table is chosen from the model name.
#
# HF_HUB_DISABLE_XET (set above) is required whenever egress goes through a
# Hugging Face mirror: current huggingface_hub releases otherwise route the
# download through the Xet CAS backend at cas-server.xethub.hf.co, which ignores
# HF_ENDPOINT, is not mirrored, and fails with HTTP 401.
RUN python -c "import tiktoken; [tiktoken.get_encoding(name) for name in ('o200k_base', 'cl100k_base')]; print('tiktoken ranks cached')" \
    && python -c "import os; from fastembed import TextEmbedding; \
        TextEmbedding(model_name=os.environ['ABB_RAG_EMBEDDING_MODEL']); print('embedder cached')" \
    && useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /opt/agent /opt/fastembed-cache /opt/tiktoken-cache

# The full upstream checkout lands here, after the dependency layer, so that its
# file mtimes cannot invalidate that layer. Owned by the runtime user because the
# upstream logger writes under agent/logs/.
COPY --chown=agent:agent agent/ ./agent/

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

ENV HOME=/home/agent
USER agent

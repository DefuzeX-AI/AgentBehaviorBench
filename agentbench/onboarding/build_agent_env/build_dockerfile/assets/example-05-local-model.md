# Example 05: CPU embeddings and preloaded assets (GPT Researcher)

The current deployment uses local Hugging Face embeddings and native research
APIs. Its complete Dockerfile provisions CPU PyTorch, embedding dependencies,
model weights and tokenizer caches before the read-only runtime starts.

The model ID/revision, provider IDs, retriever and environment values below are
specific deployment choices. They are NOT defaults for new Agents. Derive any
analogous choices from the target's supplied binding/config/source. If model
assets or large storage requirements are unknown, ask rather than invent them.
Build requires network access to the declared package/model hosts. Copying this
text does not establish a successful download or a compatible final SDK image.

Reference: `resources/agents/04-gpt-researcher/Dockerfile`.

```dockerfile
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch>=2.7,<3'
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' 'langchain-huggingface>=1,<2' 'sentence-transformers>=5,<6' \
    && useradd --create-home --uid 10001 agent
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41', local_dir='/opt/models/all-MiniLM-L6-v2', ignore_patterns=['onnx/*','openvino/*','*.h5','*.ot','*.bin'])"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# Native report-chat constructs Config("default"), which reads these official
# environment settings instead of the research entrypoint's JSON config file.
ENV EMBEDDING=huggingface:/opt/models/all-MiniLM-L6-v2 \
    EMBEDDING_KWARGS='{"model_kwargs":{"device":"cpu","local_files_only":true}}' \
    SMART_LLM=openai:gpt-4.1-mini FAST_LLM=openai:gpt-4.1-mini \
    STRATEGIC_LLM=openai:gpt-4.1-mini RETRIEVER=pubmed_central \
    TAVILY_API_KEY=""
ENV TIKTOKEN_CACHE_DIR=/opt/models/tiktoken
RUN python -c "import tiktoken; [tiktoken.get_encoding(name) for name in ('cl100k_base', 'o200k_base', 'gpt2')]" \
    && chmod -R a+rX /opt/models/tiktoken
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
```

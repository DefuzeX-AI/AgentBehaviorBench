# OntoCast in ABB

This unit runs the full native OntoCast document graph. Its input is source text,
not a chat command. `text_in_turtle_out(text_key="text")` supplies the native
InputDocument mapping, and `make_ontocast_node` owns compilation, configuration
forwarding, recursion defaults and document token budgets. The output mapping
returns the entire native AgentState using its JSON serializers.

## Windows, macOS and Linux

Use Docker with Linux containers, activate the ABB Python environment, and run
from the repository root:

```sh
python -m agentbench evaluate ontocast --sdk native --case-file resources/agents/118-ontocast/smoke-case.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/ontocast-smoke
```

Docker Desktop supports this Linux-container workflow on Windows/macOS; Docker
Engine or Desktop can be used on Linux. The Dockerfile has no fixed CPU
architecture or host drive paths. It installs the native package and provider
extras plus `documents` (docling-core), which upstream requires for extraction.
ABB supplies `.abb-runtime` during its managed image build. Runtime caches and
working data have writable directories owned by the container user.

Entity clustering also needs `sentence-transformers`. The image installs
version 5.1.1 with CPU PyTorch 2.9.1 and preloads the native default
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. The aggregation, chunking and embedding
model settings point to that same local snapshot. No encoder is substituted,
native automatic device selection is retained, and startup needs no Hugging Face
download access. The build verifies that the cached model loads locally.

## Configuration

The original generated binding already selected `Config.in_memory()`. This
native mode uses a process-local triple store and turns external vector retrieval
off. Requiring Qdrant and Fuseki secrets in the old manifest was therefore
incorrect. They are not required by this configuration.

`LLM_API_KEY` is now declared as an interceptor-managed credential instead of a
required host secret. The default OpenAI Chat Completions request is routed to
ABB's shared replacement model in `replace` mode. The native model settings and
prompts remain unchanged; the real replacement credentials stay with the
interceptor. No interception mode is hardcoded in the binding.

The ToolBox is fully initialized before graph execution and closed afterward.
No native stage is removed. Optional GPU/model-backed paths are subject to the
batch policy: record and skip when GPU model loading is required, without forcing
a CPU fallback or substituting tool results.

Inspect the returned processing state, actual model requests and trajectory.
A greeting may yield an empty domain graph because OntoCast extracts documents;
it is not expected to fabricate a conversational assistant response.

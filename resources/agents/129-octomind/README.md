# Octomind native ACP integration

Issue: #515. Source: Muvon/octomind 0.63.0 at
`aa08782640ddc441e8a0ef0f1bf25bec85344a73`. Original source is acquired through
ABB's pinned Git source preparation, stays ignored, and is not committed here.
All 712 native regular files are inventoried in `source-provenance.json`.
Official release binaries match publisher SHA256 pins for Linux amd64 and arm64;
the recipe selects the container's native CPU architecture. Actual acceptance
must state its executed platform; a second architecture is not implied by pins.

## Native execution and tools

The launcher execs the original `octomind acp developer:general`. The complete
original tap is pinned at `27691ea9486151e2ceb522f2b610132ca77335f7`, including its
symlinks, native prompts, 13 capabilities, permissions and guardrails. It is an
immutable installed snapshot, not a best-effort live Git update. Official octofs,
octocode and octobrain versions are pinned in `bootstrap/distributions.json`.
No Agent control loop, tool definition, capability or business logic is replaced.

The deployed native tool pool includes filesystem viewing/editing and shell,
structural/semantic/graph code search, memory/knowledge, web search, recall,
agent context gathering and orchestration. Native activation still decides which
capabilities are relevant to each task. Tool availability is not proof that any
tool succeeded; semantic search may require project data/indexing, and web search
still depends on admitted external services. There is no browser GUI deployment.

Official Node 22.23.4 and open-websearch 2.2.0 preserve the exact original tap
command. A global npm install alone does not warm versioned npx resolution. The
build warms the exact npm-exec package slot and metadata, then packages both.
Each Case has private writable cache metadata. Immutable installed packages,
content-addressed npm archives and ONNX weights are referenced, not copied into
ABB's memory-accounted /tmp. Cache-miss directories stay writable; native npm
uses prefer-offline, not hard offline mode. No arbitrary package/tool is filtered.

## Explicit native retrieval preset

`bootstrap/defaults/` contains byte-identical pinned dependency templates with
recorded provenance. Native configuration overrides select:

| Component | Native model selection |
| --- | --- |
| Octocode code/text embeddings | `fastembed:sentence-transformers/all-MiniLM-L6-v2-quantized` |
| Octobrain embeddings | Original `fastembed:Qdrant/all-MiniLM-L6-v2-onnx` alias, resolving to the same native quantized MiniLM model |
| Octocode/Octobrain reranking | `fastembed:jina-reranker-v1-turbo-en` |
| Octomind capability/skill embedding | Original native `muvon/octomind-embed`, unchanged |

These are supported upstream configuration choices, not altered model tensors.
Compared with upstream defaults, code/text retrieval model quality and reranker
language coverage differ. The reranker is English; multilingual ranking quality
is not promised. No reranking, indexing, GraphRAG, supervisor, compression or
permission feature flag is toggled. Original defaults such as read-only MCP
index serving remain original defaults, not integration-added disabling.

`bootstrap/local-models.json` pins 16 original public tensor/tokenizer/config
assets (211,110,711 bytes) by immutable Hub revision, byte size and SHA256.
Build-time downloads resume within bounded retries and fail closed on mismatch.
Public Hub requests refresh expiring signed redirects with a per-fetch query; the
repository revision, asset path, byte length and SHA256 remain immutable.
`prefetch_models.py` packages the native Hub cache layout; cold session startup
therefore needs no embedding download. Each Case has its own writable refs and
metadata, while immutable model weights stay in the image. Session/memory state
is not shared between Cases. Native delegated subprocesses inherit that Case's
configuration and caches. The full original template remains available separately
from generated per-Case configuration.

## Model routing and acceptance

The original main/supervisor/compression model profiles and all five Octocode
text-generation fields receive ABB's selected model through native configuration.
ABB selects the actual compatible HTTPS endpoint; the connector name does not
force the OpenRouter service. Native `OPENROUTER_API_URL` uses the loopback hop
described below. The native static octolib reqwest 0.12 client uses compiled WebPKI roots,
not the per-run CA environment. A loopback-only transport process therefore
forwards its exact bytes to the selected HTTPS target using the normal verified
ABB CA bundle and proxy. Native API configuration points to that local hop; the
actual upstream target stays HTTPS and observed by ABB. TLS verification is not
disabled, and no replies or Agent decisions are synthesized. The transport child
shares the native process group for teardown. The /models metadata request is
explicitly declared without a provider pin. Keys are supplied only
through runtime environment variables. There is no fixed provider route, secret
file in the image, replacement model reply, or shared SDK/interceptor modification.
Telemetry and npm's update notifier are disabled by their normal settings.

For this contribution, real text-generation acceptance uses only
`glm-5.3-flash`. Local model tensors above are embedding/reranking assets, not
alternate text-generation APIs. `fixtures/local-smoke/` contains a custom,
single-step filesystem/shell Smoke Case; it is not official KUMA or GT. Run it
through the ordinary ABB local SDK with a dedicated enabled evaluation registry.
The shared registration remains disabled/adapting for review. Keep Case, output,
Trace, file evidence, host acceptance and Judge results bound to the exact source
commit. Build, static checks and tool enumeration are distinct from real Smoke.
GT and its applicable Credits confirmation follow Step 1 merge. No upstream bug
report, repair PR or existing GT is used to construct source-first hypotheses.

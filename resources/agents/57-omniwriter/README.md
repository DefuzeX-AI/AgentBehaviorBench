# OmniWriter (LangGraph, production orchestrator)

Upstream: [twanew/OmniWriter](https://github.com/twanew/OmniWriter) at
`2d0aedc00552795bfa366fcbc123888042493dea` (MIT). This unit implements
[issue #381](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/381).
The ignored `agent/` directory is restored from `source-manifest.json`; no
upstream source changes are committed.

## What is deployed

`bindings/omniwriter_bridge.py` invokes the real entry point used by upstream's
`main.py`: `src.pipeline.orchestrator.WriterAgentOrchestrator`. The imported
`langgraph.json` points only at `test/search_user_agent.py`, so it is deliberately
not used as the benchmark entry point.

For a new article, the native graph routes through topic decomposition, Tavily
search, result simplification, outline generation/review, parallel chapter
writing and article assembly. The native head router can instead select its
DeepAgents branch for follow-up processing of an existing article; that branch
is not an automatic final step of new-article generation.

Each Case gets a disposable writable workspace and:

- Elasticsearch 9.3.0 plus the matching `analysis-icu` plugin, copied from the
  official image and started on loopback for native keyword retrieval;
- the upstream persistent Chroma client using the configured OpenAI-compatible
  embedding endpoint;
- the upstream Tavily search client;
- the upstream in-memory LangGraph checkpointer keyed by the Case thread ID.

The Elasticsearch process and all Case files are removed by the binding's
cleanup lifecycle. Image generation is intentionally unavailable because no
image endpoint or credential is configured; Cases must not require it.

The pinned upstream `controller_agent.py` also omits the import for the
`MessageState` type used in one runtime annotation. The binding supplies that
exact upstream type through `builtins` only while importing the module, then
restores the previous value. This is a startup compatibility shim, not a
replacement implementation.

Two pinned YAML prompts contain Jinja-style variables and literal JSON, while
their Python consumers call `str.format`. The binding escapes only the literal
braces at prompt-load time and converts those declared variables into normal
format fields; otherwise the native head router fails before its first model
call. The image also pre-caches the `cl100k_base` and `o200k_base` tokenizer
data so runtime execution does not attempt undeclared CDN egress.

The locked Python Elasticsearch 9.3.0 client removed the legacy `timeout`
constructor alias that upstream passes in addition to `request_timeout`. The
binding drops only that duplicate retired keyword before delegating to the
locked client. ABB limits the complete Case container to 1 GiB, so the binding
runs this small single-node index with a 256 MiB heap and disables unused
Elasticsearch ML/Watcher modules; the upstream 512 MiB setting otherwise causes
the Java process to be killed after the full Python graph is imported. The
binding waits for the real HTTP socket and suppresses the bundled S3 module's
irrelevant EC2 metadata probe.

The native DeepAgents branch is not a supported benchmark path:
the pinned graph routes to it without ever initializing its required
`article_post_process` state field. Registry Cases therefore use one input and
exercise the well-defined new-article chain.

## Runtime variables

Required non-secret variables:

- `LLM_BASE_URL`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`

Required secrets:

- `LLM_BASE_API_KEY` (declared as the intercepted chat credential)
- `EMBEDDING_BASE_API_KEY` (declared as the intercepted vector credential and
  selected as the host-side credential for the vector target)
- `TAVILY_API_KEY`

The chat route is OpenAI-compatible `POST
ark.cn-beijing.volces.com/api/coding/v3/chat/completions`. The committed
`model-routing.toml` keeps chat on the selected run target and sends recognized
OpenAI-compatible embedding calls to the dedicated Ark vector target. Ordinary
tool egress is limited to Tavily search and the loopback Elasticsearch
root/default-index paths used by the upstream client.

## Verification

Static validation and focused tests:

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/57-omniwriter"), plugin))
PY
pytest -q tests/test_issue381_omniwriter.py
```

The real one-Case smoke test (requires all variables above) is:

```bash
ABB_MODEL_ROUTING_CONFIG="$PWD/resources/agents/57-omniwriter/model-routing.toml" \
  python -m agentbench evaluate omniwriter --cases 1 --sdk local --no-view
```

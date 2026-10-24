# OASIS (Open Automated Security Intelligence Scanner)

Upstream: [psyray/oasis](https://github.com/psyray/oasis) at `ed3afbb3eceae1176e159406ec71cf03aebc1689` (tag `v0.7.0`, Apache-2.0).
This unit implements [Issue #378](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/378).

## What runs

`bindings/bridge.py` connects OASIS's canonical LangGraph security analysis state machine:
`START -> node_discover -> node_scan -> node_expand -> node_deep -> node_verify -> node_report -> END`
to the AgentBehaviorBench benchmark harness.

- **Conversational & Capability Routing**: Simple greetings and capability queries ("What vulnerabilities can you scan?") are answered directly by the bridge without running a full filesystem scan.
- **Source Materialization**: Code input strings and markdown blocks are written to an isolated temporary workspace directory before scanner execution.
- **LangGraph Config & OpenTelemetry**: Passes `config=config` and sets `set_config_context` so ABB tracing callbacks capture graph node spans.

## Validated Providers and Models

OASIS requires two independently configured model backends:
1. **Chat Model (Scan & Deep Analysis)**:
   - Validated models: `deepseek-chat`, `deepseek-flash`
   - Provider: `openai` (`--provider openai`)
   - Endpoints: Configured via `OPENAI_BASE_URL` / `DEEPSEEK_BASE_URL` and `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`.
2. **Embedding Model (Vulnerability & Source Vectorization)**:
   - Validated model: `text-embedding-3-small`
   - Provider: `openai` (`--embed-provider openai`)
   - Endpoints: Configured via `OASIS_EMBED_OPENAI_BASE_URL` / `OPENAI_EMBEDDING_BASE_URL` and `OASIS_EMBED_OPENAI_API_KEY` / `OPENAI_EMBEDDING_API_KEY` (falling back to `OPENAI_BASE_URL` / `OPENAI_API_KEY` if not set).

### Split-Backend Routing Notice
Because DeepSeek and many specialized OpenAI-compatible LLM endpoints do not serve an `/embeddings` route, chat and embedding traffic are routed independently:
- Chat requests (`POST /v1/chat/completions`) go to `OPENAI_BASE_URL`.
- Embedding requests (`POST /v1/embeddings`) go to `OASIS_EMBED_OPENAI_BASE_URL`.

## KUMA / Benchmark Configuration

When running KUMA Local Smoke or evaluations, configure the models as:
- Chat model: `deepseek-chat` (or `deepseek-flash`)
- Embedding model: `text-embedding-3-small`

Environment variables forwarded by `agent.toml`:
- `OPENAI_MODEL`: Chat model name (`deepseek-chat` / `deepseek-flash`)
- `OPENAI_EMBEDDING_MODEL` / `EMBED_MODEL`: Embedding model name (`text-embedding-3-small`)
- `OPENAI_BASE_URL`: Chat API base URL
- `OASIS_EMBED_OPENAI_BASE_URL`: Embedding API base URL

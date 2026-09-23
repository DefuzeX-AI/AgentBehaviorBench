# open-notebook (LangGraph, hand-written configuration)

Upstream: [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) @
`3127f14ea9dbb519f0e4ddc64a0742ca644ba6ef` (MIT), snapshot in `agent/` unchanged except the
added descriptor `agent/abb-langgraph.json` (upstream ships no `langgraph.json`; it only
names upstream's compiled chat graph `open_notebook/graphs/chat.py:graph`).

## What is deployed

The notebook **chat** graph, driven by `bindings/bridge.py` the way upstream's API drives it
(`api/main.py` lifespan migrations + `api/routers/chat.py` create_session / build_context /
execute_chat), without FastAPI or the Next.js UI:

- SurrealDB v2.6.5 (the binary from `surrealdb/surrealdb:v2.6.5`, same major as upstream's
  `docker-compose.yml`) runs **in the Agent container** in memory mode on `127.0.0.1:18765`,
  as upstream's own `single` image target runs it in-container. Upstream's migrations are
  applied per Case; the database is discarded on close.
- One `openai_compatible` language model named `$GLM_MODEL` is registered and set as the
  default chat model. Endpoint/key come from upstream's documented env fallback
  (`OPENAI_COMPATIBLE_BASE_URL` / `OPENAI_COMPATIBLE_API_KEY`), mapped from
  `GLM_API_BASE_URL` / `GLM_API_KEY`.
- One empty Notebook and one ChatSession per Case. Each Case Input is one user chat
  message; the reply is the last AI message. Multi-turn history lives in upstream's
  SQLite checkpointer (thread = chat session id) for the Case only.

Not deployed: sources/uploads, embeddings and vector search (ABB rewrites every wire's
`model`, which would break the embeddings call), the Ask graph, source chat,
transformations, podcasts. The chat graph has no tools.

## Provider variables

`GLM_API_KEY` (intercepted credential), `GLM_API_BASE_URL`
(`https://open.bigmodel.cn/api/coding/paas/v4`), `GLM_MODEL`. The model route is the
OpenAI-chat protocol on `open.bigmodel.cn` `/api/coding/paas/v4/chat/completions`.

## Network

Only the model route plus the loopback SurrealDB WebSocket upgrade
(`GET 127.0.0.1:18765/rpc`, `network/rules.toml`); ABB redirects loopback TCP through the
interceptor too. No external egress.

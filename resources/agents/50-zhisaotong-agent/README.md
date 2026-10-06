# Zhisaotong Robot Vacuum Support Agent (LangGraph unit)

Upstream: [bamboo-moon/zhisaotong-Agent](https://github.com/bamboo-moon/zhisaotong-Agent) at
`92569e61ac22ef4d902953a7d916e941921ab92f`. The checkout is acquired from Git
(`[source] method = "git"`) and is not committed: `prepare_agent_source()` restores this
exact revision into `agent/` before an evaluation opens, the same way
`resources/agents/12-minimax-code` does. No descriptor was added because upstream builds
its graph from a Python factory rather than a `langgraph.json`, so `agent.toml` declares
the outer binding `bindings/bridge.py:create_graph` with `output_key = "answer"`.

Upstream declares no license. The repository ships no `LICENSE` file and its README
states the code is for learning and reference use only. Nothing under `agent/` is
modified: the revision in `[source]` is the provenance record, and the build consumes the
restored tree unchanged.

## What runs

Upstream `app.py` is a Streamlit front end only. The application logic is
`agent.react_agent.ReactAgent` -- a LangChain `create_agent(...)` ReAct graph built from
`prompts/main_prompt.txt` with seven tools and three middlewares. `app.py` drives it
through `ReactAgent.execute_stream(query)`, a generator over
`agent.stream(..., stream_mode="values")`. The binding invokes the same compiled graph
with `ainvoke` instead, so the benchmark's callbacks, tags and thread settings reach the
native model, tool and middleware calls; both paths pass the same runtime context
(`context={"report": False}`), which the `report_prompt_switch` middleware reads.

Seven tools, exactly the upstream set: `rag_summarize`, `get_weather`,
`get_user_location`, `get_user_id`, `get_current_month`, `fetch_external_data`,
`fill_context_for_report`. The Case Input is the user's Chinese product-support
question; the reply is the final assistant text under `answer`.

`bindings/bridge.py` supplies a `model.factory` module exposing the two names the Agent
imports -- `chat_model` and `embed_model` -- because upstream's factory builds `ChatTongyi`
and `DashScopeEmbeddings`, which speak DashScope's native protocol. **No upstream file is
modified.**

## Environment

- `OPENAI_API_KEY` (intercepted credential; ABB injects a placeholder and substitutes the
  target key). `chat_model` is an OpenAI-protocol client, which is what
  `[[llm_interception.routes]]` declares for `POST api.openai.com /v1/chat/completions`.
  Run ABB with the target model variables (`OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` /
  `OPENROUTER_MODEL`) pointing at the model under test.
- No Amap credential. `get_weather` and `get_user_location` need an Amap web-service key
  and egress to `restapi.amap.com`; neither is provided, and upstream already converts
  those failures into the Chinese error strings it hands back to the model. The tools stay
  enabled and degrade exactly as written.

## Network

Only the model route `POST api.openai.com /v1/chat/completions`. No tool routes are
declared, so a Case that makes the Agent call `get_weather` or `get_user_location` reaches
an undeclared host and gets the upstream failure string -- the intended, expected result.

The RAG embedder is a CPU-only ONNX model (`BAAI/bge-small-zh-v1.5` via `fastembed`) baked
into the image at build time, so `rag_summarize` needs no second model target and no extra
credential. The tiktoken ranks are pre-cached for the same reason: `tiktoken` otherwise
fetches its BPE tables from `openaipublic.blob.core.windows.net` on first use.

## Knowledge base

Two upstream facts this deployment has to work around, both recorded rather than patched:
the restored tree keeps them exactly as the upstream revision committed them.

1. The upstream `chroma_db/chroma.sqlite3` holds the `agent` collection with **zero**
   embeddings, while `md5.text` already records the MD5 of all six source documents, so
   `VectorStoreService.load_document()` skips every file and the retriever returns nothing
   -- the upstream revision as published has a non-functional `rag_summarize`.
2. `data/` ships six documents (one PDF, five text files) that are unreachable through that
   index.

The binding rebuilds the index once, into its own temporary directory, and points
`md5_hex_store` at a fresh ledger so the recorded hashes do not suppress indexing. Upstream
code, prompts and data are unchanged: the restored corpus is what `rag_summarize` reads.

## Not deployed

The Streamlit UI (`app.py`), the Amap-backed tools' happy path, and any live customer
system: `fetch_external_data` reads only the bundled sample ledger for user ids 1001-1010,
and `get_user_id` / `get_current_month` return random entries from hard-coded lists.

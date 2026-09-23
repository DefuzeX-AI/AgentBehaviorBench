# local-deep-research (LangGraph unit)

Upstream: [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research)
at `ede8a7b4a8ac746db176285e1075f327e188be00` (package version 1.10.7), imported with
`agentbench agent add`. The upstream `tests/` directory (45 MB of test fixtures) is left out of
this snapshot; nothing else under `agent/` is modified. The only addition is
`agent/abb-langgraph.json`, a minimal graph descriptor (upstream has no `langgraph.json`).

## What runs

`bindings/ldr_bridge.py` calls the documented programmatic API
`local_deep_research.api.quick_summary()` with the upstream default research strategy
`langgraph-agent`. That strategy is a LangChain 1.x `create_agent` graph (LangGraph) with a
`web_search` tool and a `research_subtopic` tool that starts parallel `create_agent` sub-agents.
The Case Input is the research question; the reply is the report text (`summary`). Sources and
formatted findings are kept in the raw output.

Deployment settings (upstream setting keys, passed through `create_settings_snapshot`):

| Setting | Value | Why |
| --- | --- | --- |
| `llm.provider` | `openai` | ChatOpenAI → `api.openai.com`, intercepted by ABB and routed to the target model |
| `search.tool` | `wikipedia` | keyless search engine; no search API key needed |
| `search.engine.web.<other>.agent_enabled` | `false` | only Wikipedia is offered to the agent |
| `policy.egress_scope` | `public_only` | upstream `strict` denies every public host, including Wikipedia |
| `search.fetch.mode` | `disabled` | removes the arbitrary-URL `fetch_content` tool (outside the egress allow-list) |
| `langgraph_agent.max_iterations` / `max_sub_iterations` / `max_subagent_workers` | `15` / `5` / `2` (upstream 50 / 8 / 4) | bounded budget: with defaults a 2-step KUMA Case made ~270 model calls and ~1900 Wikipedia requests and hit the 2400 s execution timeout |
| `search.max_results`, `search.engine.web.wikipedia.default_params.max_results` | `10` (upstream 50 / 20) | same |

The binding's `ainvoke` runs the synchronous API on the worker's main thread on purpose:
upstream's `@no_db_settings` guard refuses callers on a non-`MainThread` thread that has no web
request context ("Database access attempted from background thread").

## Environment

- Model: the standard ABB target-model variables (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`,
  `OPENROUTER_MODEL`). Any OpenAI-compatible chat model with tool calling works.
- No tool credentials. Egress: `en.wikipedia.org` `/w/api.php` (GET, ports 80 and 443; the
  `wikipedia` package first uses http and follows the https redirect).

The image installs CPU-only torch before the upstream package, so `sentence-transformers`
does not pull CUDA wheels (image ≈ 3.3 GB; the first build takes about 15 minutes).

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
| `search.tool` | `wikipedia` | keyless primary search engine (upstream default SearXNG needs a self-hosted instance) |
| `search.engine.web.tavily.api_key` | `$TAVILY_API_KEY`, only when set | enables Tavily as an extra engine |
| `policy.egress_scope` | `public_only` | upstream `strict` denies every public host, including Wikipedia |
| `langgraph_agent.max_iterations` / `max_sub_iterations` / `max_subagent_workers` | `15` / `5` / `2` (upstream 50 / 8 / 4) | bounded budget: with defaults a 2-step KUMA Case made ~270 model calls and ~1900 Wikipedia requests and hit the 2400 s execution timeout |
| `search.max_results`, `search.engine.web.wikipedia.default_params.max_results` | `10` (upstream 50 / 20) | same |

The binding's `ainvoke` runs the synchronous API on the worker's main thread on purpose:
upstream's `@no_db_settings` guard refuses callers on a non-`MainThread` thread that has no web
request context ("Database access attempted from background thread").

## Environment

- Model: the standard ABB target-model variables (`OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`,
  `OPENROUTER_MODEL`). Any OpenAI-compatible chat model with tool calling works.
- Optional tool credential: `TAVILY_API_KEY` (`optional_secret_env_keys`) adds the Tavily engine.

## Web tools and egress

The other search engines keep their upstream `agent_enabled` defaults. Keyed engines are dropped
by upstream when no key is set, so without `TAVILY_API_KEY` the agent is offered the keyless
arXiv, PubMed, OpenAlex, Semantic Scholar, Wikinews and Wayback engines besides the primary
Wikipedia `web_search`. `search.fetch.mode` keeps the upstream default (`summary_focus_query`),
so `fetch_content` is available.

`agent.toml` declares each engine's API and the common page hosts (Wikipedia `/wiki/*`, arXiv
`/abs/*` and `/pdf/*`, PubMed and PMC articles, Wayback snapshots) as tool routes, so these calls
are forwarded and recorded as tool evidence. Any other URL `fetch_content` opens goes to ABB's
egress observer, which records it in `egress.jsonl` and refuses it with 403 unless it is on the
allowlist (`ABB_EGRESS_ALLOW` adds hosts). A refusal reaches the agent as a tool error and does
not reject the Case (#137).

Before #137 an undeclared request made the interceptor reject the whole trace, so this unit
originally disabled `fetch_content` and hid every engine except Wikipedia.

The image installs CPU-only torch before the upstream package, so `sentence-transformers`
does not pull CUDA wheels (image ≈ 3.3 GB; the first build takes about 15 minutes).

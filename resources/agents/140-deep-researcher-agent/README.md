# NVIDIA Deep Researcher Agent in ABB

The integration selects upstream revision `951a1a1114e9818073ddbe2a5fdbfa824751f4d3`
(version 2.2.0, Apache-2.0). It runs the native NeMo Agent Toolkit workflow whose
agents use LangGraph. `bindings/bridge.py` mirrors the public CLI lifecycle:
`load_workflow` → `SessionManager.session` → `session.run` → `runner.result`.

## Prepare the source

The pinned tree has internal directory/file symlinks in its skill guidance.
ABB's supported Git staging rejects these directory links. This unit therefore
uses **bundled/manual source**, not unattended automatic Git restoration:

```bash
git clone https://github.com/NVIDIA-AI-Blueprints/deep-researcher-agent /tmp/deep-researcher-source
git -C /tmp/deep-researcher-source checkout 951a1a1114e9818073ddbe2a5fdbfa824751f4d3
python resources/agents/140-deep-researcher-agent/prepare_source.py /tmp/deep-researcher-source
```

The source checkout must be the clean Git root, including no ignored files.
The helper verifies the exact revision, rejects unsafe links and an existing
`agent/`, materializes internal links, and compares resulting file bytes with
their pinned originals. Never commit `agent/`.

## Deployment

The native `configs/config_cli_default.yml` supplies all agents, source registry,
Tavily tools, native prompts, escalation behavior and research limits. The
binding changes only documented operator configuration:

- Headless `enable_clarifier=false`, as in native `config_mcp.yml`, avoids requiring
  a human responder. Deep research runs inline rather than through a Dask job.
- Each native LLM profile uses NAT's OpenAI-compatible provider and ABB's intercepted
  shared model. Native temperatures, top-p, token limits, retry counts and explicit
  `parallel_tool_calls=false` are preserved. NIM-specific `chat_template_kwargs`
  are omitted because the shared provider is not a hosted NIM model; native NIM
  model identities are replaced by the selected shared provider/model.
- `LANGCHAIN_OPENAI_TCP_KEEPALIVE=0` selects the native client's supported proxy-compatible transport behavior. Build-only host proxies are not inherited by runtime containers; normal ABB transparent interception remains active.
- A private SQLite file supplies native checkpoint persistence within one Case.
  ABB's thread ID maps to NAT's conversation context. Incoming live RunnableConfig
  is inherited by LangChain nested calls rather than serialized or discarded.
- NAT's async session/manager are closed; its otherwise globally cached SQLite
  saver for this private path is evicted and its connection explicitly closed.
  No cross-Case source registry or checkpoint is intentionally shared.

Python 3.12 is supported by upstream's `>=3.11,<3.14` declaration. The Docker image
installs the root package and native Tavily package from the **frozen upstream
workspace lock**, including the pinned NeMo Relay Git source. It does not install
additional paper/enterprise source packages, UI/API frontend or sandbox services.

`TAVILY_API_KEY` is an optional secret at process startup, matching upstream's
native absent-key error path. **Real research requires a valid key**. Without it,
only startup/meta conversation and truthful source-unavailability behavior can
be checked; that does not satisfy research acceptance. Model traffic is
intercepted at OpenAI Chat, with explicit POST `/search` egress to Tavily. No
other tool network access is configured.

The source provenance, actual validation and remaining acceptance blockers are
recorded in `docs/validation/issue479-deep-researcher/README.md`. This unit is
registered disabled/adapting. GT starts only after the onboarding PR is merged.

# NVIDIA Deep Researcher in ABB

The original generated unit mistakenly launched an HTTP FastMCP service as a
stdio ACP agent. This unit uses ABB's LangGraph binding contract and the upstream
`deep_researcher_mcp.workflow_runner.WorkflowRunner`, which loads the complete
native NAT-owned LangGraph. It does not emulate ACP or bypass intent routing.

## Windows, macOS and Linux

Use Docker with Linux containers, activate the ABB Python environment and run
this command from the ABB repository root:

```sh
python -m agentbench evaluate deep-researcher-agent --sdk native --case-file resources/agents/170-deep-researcher-agent/smoke-case.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/deep-researcher-smoke
```

Use Docker Desktop on Windows/macOS and Docker Engine/Desktop on Linux. The
Dockerfile has no host drive paths or fixed CPU architecture. It preserves the
upstream MCP lock's relative main-package and source-package layout and installs
its frozen production dependency closure. ABB supplies `.abb-runtime` during
its managed build. Native source is bundled and must be supplied with the unit.

## Model and tool configuration

`bootstrap/configure.py` derives a runtime YAML from pinned `config_mcp.yml`.
Only its `llms` section changes: the native supported OpenAI client replaces NIM,
with a conventional source model and endpoint. The NIM-only
`chat_template_kwargs` field is removed; remaining sampling and token settings
are preserved. An assertion verifies all non-model sections are identical.
Native prompts and tool implementations are never edited.

In `replace` mode ABB injects an `OPENAI_API_KEY` placeholder and the interceptor
owns the real replacement provider credentials. The actual target model comes
from ABB's shared model settings, not from the source-side `gpt-4o` label. Do not
add NVIDIA or OpenAI keys to `runtime.secret_env_keys` for this workflow. Shared
interception policy controls the mode; the binding contains no mode switch.

`TAVILY_API_KEY` is an optional secret forwarded when available. Without it,
upstream registers its explicit unavailable-search tools; greeting startup still
works. Full web research needs that credential and applicable network routes.
The binding uses the native workflow directly, so SQLite checkpoints suffice
without starting the MCP HTTP server or its PostgreSQL job ledger.

Each input owns its WorkflowRunner lifecycle and closes it afterward. The
binding returns the full native terminal success object and propagates failures.
Inspect `trajectory.json`, actual input output and replacement traffic together;
a file alone does not establish success.

# EvoScientist (LangGraph unit)

Upstream: [EvoScientist/EvoScientist](https://github.com/EvoScientist/EvoScientist) at
`22dd14f1b6ffaf92da58b657086332d9aa3afe78` (tag `v0.3.2`, Apache-2.0), imported with
`agentbench agent add`. The `agent/` snapshot is the unmodified upstream tree; no descriptor
was added: `agent.toml` points at upstream's own `EvoScientist/langgraph_dev/langgraph.json`,
graph `EvoScientist` (`EvoScientist.langgraph_dev.main_graph:EvoScientist_agent`).
`agent add -b` was not used; `agent.toml`, `Dockerfile`, `requirement.md` and
`bindings/bridge.py` are hand-written.

## What runs

The main EvoScientist deep agent (deepagents `create_deep_agent`): orchestrator with
planner / research / code / debug / data-analysis / writing sub-agents (`task` tool),
`think_tool`, `skill_manager`, file-system tools and a sandboxed `execute` shell in the
workspace, QuickJS code interpreter, todo list and memory middleware.

`bindings/bridge.py` builds that graph the way upstream's one-shot CLI does
(`EvoSci -p "..." --auto-mode`): `get_effective_config(cli_overrides)` then
`create_cli_agent(workspace_dir=..., config=...)` with an in-memory checkpointer; the ABB
session id is the LangGraph `thread_id`. The Case Input is the user message; the reply is the
last AI message text. The message list and workspace file names are kept in the raw output.

Deployment settings (upstream config keys):

| Setting | Value | Why |
| --- | --- | --- |
| `provider` / `model` | `zhipu-code` / `$GLM_MODEL` | upstream's built-in GLM Coding Plan provider; ABB intercepts its route |
| `auto_mode` (+ `auto_approve`, `enable_ask_user=false`) | on | upstream's unattended mode; run config sets `configurable.hitl_suppressed=true` as upstream's gateways do |
| `enable_async_subagents` / `enable_scheduler` | off | no `langgraph dev` sidecar; writing / data-analysis sub-agents run in-process (upstream's documented setting for one-shot runs) |
| `memory_workers_enabled` / `memory_skill_synthesis_enabled` | off | cross-session background workers cannot persist in a one-shot container |
| `recursion_limit` | 150 (upstream 1,000,000) | bounds one turn to the container timeout |

All writable state (workspace, data dir, `XDG_CONFIG_HOME`) is a fresh directory under `/tmp`.

## Environment

- `GLM_MODEL` (model name), `ZHIPU_API_KEY` (intercepted credential; ABB injects a
  placeholder and substitutes the target key). Run ABB with the target model variables
  (`OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` / `OPENROUTER_MODEL`) pointing at the model
  under test.
- No `TAVILY_API_KEY`: upstream omits `tavily_search`, so there is no web search.

## Network

Only the model route `POST open.bigmodel.cn /api/coding/paas/v4/chat/completions`.
No tool routes. `skill_manager` install/browse (GitHub) is not declared, so a Case that makes
the agent install a skill would reach an undeclared host.

## Not deployed

Web search (Tavily), MCP servers, the `langgraph dev` / WebUI / TUI surfaces, async
sub-agents, cron scheduler, chat channels, OAuth providers, cross-session memory.

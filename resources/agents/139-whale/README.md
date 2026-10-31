# Whale native ACP integration

This unit builds the unmodified `cmd/whale-acp` server at the revision recorded
in `agent.toml`. Upstream currently describes the project as no longer maintained;
this integration remains pinned to Whale, not its suggested replacement.

## Reproduce

Use the repository setup instructions and Docker. Source preparation retrieves
and verifies the pinned Git tree before building the Go 1.26.2 binary. The ignored
`agent/` directory is generated source, never a committed integration artifact.

Provide `DEEPSEEK_API_KEY` through the private environment file. Select
`--model deepseek-v4-pro` explicitly. The launcher requires runtime-selected
DeepSeek provider, model, endpoint and credentials and maps them into the native
server's environment. It does not substitute another provider or rename a model.

At the 2026-10-26 authenticated model-catalog check, the service exposed
`deepseek-flash` and `deepseek-v4-pro`; the pinned ACP server accepts
`deepseek-v4-flash` and `deepseek-v4-pro`. Only their exact intersection is enabled.
The default `deepseek-flash` therefore fails clearly. Native `WHALE_API=auto`
selects Chat Completions for Pro. The `source="native", runtime_configurable=true` capability retains the native
provider restriction while using runtime-owned selection. Interception observes that actual
protocol using runtime-owned routes; no Responses translation is introduced.

The registry entry stays disabled and `adapting`. For a bounded evaluation, copy
its entry into a temporary registry beneath `resources/`, set `enabled=true`, and
run the documented `agentbench evaluate` command with that registry and explicit
model selection. Keep the tracked registry unchanged. No credentials belong in
this directory, a report, or an evidence archive.

## Capability boundary

`requirement.md` describes the native tools and the empty Case workspace. External
tool egress, MCP services and LSP servers are not provisioned. Native tool and
permission handling are unchanged. Configuration validation, real execution,
Judge findings and certification are separate acceptance stages.

See [current PR closeout](evaluation/2026-10-26-closeout.md) for slot numbering,
synchronization checks and preserved historical evidence boundaries.

## Runtime dependency

This unit requires the separately proposed ABB native runtime model selection
capability (`model.runtime_configurable`). Current ABB main rejects that field,
so this unit cannot run on main until the core change is merged.

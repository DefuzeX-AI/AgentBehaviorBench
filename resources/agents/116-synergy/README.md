# Synergy native ACP

Pinned source: SII-Holos/synergy at
`d82f52e4d137831dc3dfdf5ac186c0cb9b5ab584` (workspace packages 1.1.26).
The source pins Bun 1.4.3; its original ACP command and full preset runtime are used.

## Manual source prerequisite

This is a bundled-source unit because upstream contains an internal symbolic link
at `apps/web/src/custom-elements.d.ts`. ABB's automatic Git acquisition rejects
symbolic links. Source is ignored and must not be committed. Prepare the source
in a Linux filesystem before evaluation, preserving this link:

```sh
git clone https://github.com/SII-Holos/synergy.git resources/agents/116-synergy/agent
git -C resources/agents/116-synergy/agent checkout --detach d82f52e4d137831dc3dfdf5ac186c0cb9b5ab584
```

The link resolves inside the source tree. ABB's existing build staging
materializes internal file links; no source logic is edited. A missing source
directory must remain a preparation failure rather than silently downloading
another release or substituting an Agent.

## Configuration

The outer launcher writes native domain configuration under a fresh private
`SYNERGY_HOME`, selects Forge and the guarded control profile, and starts the
original `createAcpCommand` with `PresetRuntimeHandle.open` and loopback HTTP.
At this revision, native ACP request handlers call scoped APIs without a Scope
context; direct session/new fails with "No context found for scope". The outer
TypeScript bootstrap enters the live preset Runtime with its native `run` method
and binds five native request handlers using `withScopeContext` for this Case
directory. It supplies the same Runtime handle to the original ACP command;
there is no second CLI store or replacement protocol implementation.
The handlers' bodies, tools, sub-agents, prompts, compaction and reasoning loop
are unchanged. This revision-dependent hosting adjustment is part of the
integration and requires review. Ordinary ACP permissions use allow_once.

The native `guarded` capability rules remain enabled, but native
`sandbox.enabled=false` selects the ABB worker as the OS isolation boundary.
Commands run inside that nonroot worker, without an additional per-command
bubblewrap boundary. This is an explicit deployment setting, not equivalent to
the original nested-sandbox deployment. It does not switch to `full_access` or
change ABB's Docker capabilities, no-new-privileges, resource limits or network
interception. Offline comparison under the same Docker policy confirmed that
file reads remain allowed, external writes ask, and hardline shell operations
remain denied, while Python execution succeeds. It does not prove containment
against arbitrary Agent behavior inside the container; native shell filesystem
isolation is absent and this limitation matters for future GT interpretation.

The selected runtime model uses native OpenAI-compatible provider configuration,
with context/output deployment budgets of 131072/8192 tokens. The credential is
an `{env:ABB_AGENT_MODEL_API_KEY}` reference, not a saved key. All model settings
come from runtime-owned `ABB_AGENT_MODEL_*` variables. Proxy and CA settings are
preserved; only loopback IPC is added to NO_PROXY. Model catalog refresh is
disabled through the native upstream flag because this deployment supplies its
selected model explicitly.

The runtime has all its default preset components. No Desktop/Electron GUI,
external MCP server, Holos account, external coding Agent or hosted service is
provisioned. The Docker build skips the Electron GUI binary download; it does
not remove Agent tools. The native Linux sandbox helper and PTY are built from
pinned source with locked Cargo dependencies; the native watcher is built with
upstream's script. Actual sandbox/command availability must be established by
real acceptance before readiness.

The unit stays disabled/adapting pending integration review. The later two-input
Local Smoke passed with stdout 20 then 26, exit 0, native ACP approvals and a
local Judge pass/high. See the [acceptance record](../../../docs/validation/issue493-synergy/README.md)
for the explicit container-boundary deployment, Judge transport, retained
failure and evidence scope; see `requirement.md` for deployed behavior.

## Earlier failed acceptance

The packaged image passes offline ACP initialize/session-new/clean-exit checks.
A real two-input Local Smoke completed file creation, editing and readback in
one native session, but the shell could not run Python: bubblewrap returned
`No permissions to create new namespace` under ABB's default Docker policy.
The source-built sandbox helper was present and invoked; this is not a missing
helper fallback. No Docker privileges or native permission profile were relaxed.

Native long-term memory writes also failed because no embedding API was
configured and the default local model could not be downloaded. The Agent could
still recall the conversation label from its ongoing session. The local Judge
returned no JSON object, so that attempt has no successful Judge report. The CLI exited
1, while execution transport, trace validation and cleanup completed.

That failed attempt is not certification or a GT result. No official KUMA
Case/Judge calls were made. Complete failed-attempt evidence is retained locally.
The later container-boundary deployment described above uses the native sandbox
configuration option and keeps guarded approvals. The ordinary session-continuity
Case explicitly requests conversation context, not durable memory storage;
long-term memory remains unavailable without provisioned embedding assets/API.

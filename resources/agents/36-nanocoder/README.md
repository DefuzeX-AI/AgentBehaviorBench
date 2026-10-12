# Nanocoder ACP deployment

This unit installs the pinned [Nanocoder](https://github.com/Nano-Collective/nanocoder)
CLI, npm package `@nanocollective/nanocoder@1.30.0` (npm `gitHead` `59874391`),
and runs its built-in ACP server (`nanocoder --acp`, `source/acp/acp-server.ts`).
ABB invokes it over ACP stdio and keeps each Case in a separate empty workspace.
No upstream source is vendored or modified.

## Licence

`@nanocollective/nanocoder` is MIT (`LICENSE.md` in the package). The unit only
installs the unmodified npm package and its dependencies at build time.

## Model provider

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

## Distribution

`install/package.json` pins `@nanocollective/nanocoder` `1.30.0`;
`install/package-lock.json` records the resolved tree with npm integrity hashes.
The Dockerfile runs `npm ci --omit=dev` on `node:24-bookworm` (package engine:
Node >= 22) and checks that the CLI loads.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment), creates a disposable per-Case `HOME` under `/tmp` with XDG
directories inside it, points `NANOCODER_CONFIG_DIR`, `NANOCODER_DATA_DIR` and
`NANOCODER_LOG_DIR` there (preferences, session store and file logs), and then
`exec`s Nanocoder, which owns the ACP stdio channel directly.

- It pre-seeds `$XDG_CACHE_HOME/nanocoder/models.json` with an empty, unexpired
  models.dev catalog. Nanocoder otherwise fetches `https://models.dev/api.json` for
  context-limit lookups and for the per-response pricing it attaches to ACP usage;
  that host is not admitted. With the empty catalog both lookups return "unknown"
  (no context-window based auto-compaction, no cost figure) and no request is made.
- It drops `NANOCODER_LOG_LEVEL` (console logging would write to stdout, the
  JSON-RPC channel), `NODE_ENV`, and inherited provider/MCP file overrides.

Nanocoder has no startup update check or telemetry on the ACP path (the update
checker runs only in the interactive TUI). `web_search` is unregistered upstream
when no Brave Search key is configured, and none is.

## Permissions and questions

ACP sessions start in Nanocoder's `auto-accept` mode (upstream default). Read-only
tools run unattended; tools that change state (for example `execute_bash`) send
ACP `session/request_permission` with `allow` / `deny` options, which ABB answers
with its `allow_once` policy. The `ask_user` tool is also surfaced as a permission
request whose options are the question's choices (all `allow_once`), so a headless
run never blocks: ABB selects the first choice.

## Evidence

Nanocoder executes its tools itself (not through ACP `fs/*` or `terminal/*`
delegation). ACP evidence consists of `tool_call` / `tool_call_update`
notifications, streamed `agent_message_chunk` text and prompt usage. File effects
are captured by ABB's workspace file evidence, and model traffic by the interceptor.

## Known behavior

- At startup Nanocoder clears its task list by writing `.nanocoder/tasks.json`
  (`[]`) in the working directory, so every Case workspace contains that file even
  when the agent changed nothing.
- Nanocoder loads a `.env` file and a project `agents.config.json` from the
  working directory if a Case creates them; the launcher's environment provider
  still takes precedence for `abb-shared`.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Earlier acceptance records describe the previous fixed-provider deployment. They do not
certify every shared provider/model combination; run a fresh Case after changing it.

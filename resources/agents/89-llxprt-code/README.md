# LLxprt Code ACP deployment

This unit installs the pinned [LLxprt Code](https://github.com/vybestack/llxprt-code)
release, npm package `@vybestack/llxprt-code@0.11.0`, and runs its built-in ACP
server (`llxprt --experimental-acp`, `packages/cli/src/zed-integration/`). ABB
invokes it over ACP stdio and keeps each Case in a separate empty workspace. No
upstream source is vendored or modified.

The recorded source revision `5400f65a` is tag `v0.11.0`, which is also the npm
package's `gitHead`. LLxprt Code is a multi-provider fork of Google's Gemini CLI.

## Licence

Apache-2.0 (`LICENSE` in the repository and in the npm package). The unit only
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

LLxprt's `openai` provider uses the OpenAI SDK and posts to
`<baseurl>/chat/completions`, which is the exact route the runtime admits.

## Distribution

`install/package.json` pins `@vybestack/llxprt-code` `0.11.0`;
`install/package-lock.json` records the resolved tree (589 entries, all from
`registry.npmjs.org` with npm integrity hashes). The Dockerfile runs
`npm ci --omit=dev` on `node:24-bookworm` (package engine: Node >= 24) and checks
that the CLI starts. The published `llxprt` bin is a Node shim that runs the
prebuilt `bundle/llxprt.js` on the Bun runtime shipped as the `bun` /
`@oven/bun-linux-*` npm dependencies. Install scripts stay enabled: they place
the Bun binary and set up `node-pty` and the tree-sitter / ast-grep grammars.

`ripgrep` is installed from Debian for local search.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment), creates a disposable per-Case `HOME` under `/tmp` with XDG
directories inside it (LLxprt resolves its config, data, cache and log roots from
them), and then `exec`s
`llxprt --experimental-acp --provider openai --baseurl <ABB_AGENT_MODEL_BASE_URL> --model <ABB_AGENT_MODEL>`,
which owns the ACP stdio channel directly.

- The key is passed as `OPENAI_API_KEY`, which LLxprt's `openai` provider reads when
  no `--key`, `--keyfile`, keyring entry or profile key is given. It never appears
  in argv or on disk.
- It writes a user `settings.json` that disables auto-update and update
  notifications (npm registry) and usage statistics, and keeps OpenTelemetry
  export and the IDE companion off.
- It pre-seeds `<cache>/llxprt-code/models.json` with an empty models.dev catalog.
  LLxprt's model registry otherwise fetches `https://models.dev/api.json`; that
  host is not admitted. With the empty catalog no request is made, and context and
  pricing metadata for the selected model are unknown.
- It sets `LLXPRT_DISABLE_OS_KEYRING=1` (no secret service in the container) and
  drops inherited Gemini/Google, Anthropic and OpenAI credentials, `LLXPRT_*`
  storage/profile overrides and debug switches, so no Google sign-in, Vertex or
  other provider path is reachable.

LLxprt sends no usage telemetry upstream (unlike Gemini CLI, its bundle contains
no Clearcut endpoint), and the startup update check runs only in the interactive
UI. The acceptance run's `egress.jsonl` records no outbound attempt besides the
model route.

## Tools and permissions

The model sees 28 tools: `read_file`, `read_many_files`, `read_line_range`,
`ast_read_file`, `list_directory`, `write_file`, `replace`, `ast_edit`,
`insert_at_line`, `delete_line_range`, `apply_patch`, `glob`,
`search_file_content`, `ast_grep`, `structural_analysis`, `run_shell_command`,
`check_async_tasks`, `todo_write`, `todo_read`, `todo_pause`, `save_memory`,
`exa_web_search`, `codesearch`, `direct_web_fetch`, `task`, `list_subagents`,
`generate_image` and `github`. The unit does not disable any of them.

- `exa_web_search` and `codesearch` post to the keyless Exa MCP endpoint
  `https://mcp.exa.ai/mcp`, declared as an optional tool route in
  `network/rules.toml` (the same route as `12-opencode`). `direct_web_fetch`
  contacts the URL the model chooses; that traffic goes to ABB's egress observer,
  which forwards allowlisted hosts and refuses others with 403. A refusal is Agent
  behavior and does not reject the Case.
- `task` / `list_subagents` find no configured subagent, `generate_image` has no
  image backend (it needs a signed-in Codex account and reports the tool as
  disabled), and `github` drives a `gh` CLI that the image does not contain.

ACP sessions start in LLxprt's `default` approval mode. Read-only tools run
unattended; writes, edits and shell commands send ACP `session/request_permission`
(options `proceed_always` / `proceed_once` / `cancel`, kinds `allow_always` /
`allow_once` / `reject_once`), which ABB answers with its `allow_once` policy
(`proceed_once`). The session is never switched to `autoEdit`
or `yolo`.

## Evidence

LLxprt runs file tools itself and runs shell commands through ACP client
terminals when the client offers them (ABB does: the acceptance run records a
terminal start, output, exit and release for each command, run as `bash -c` in
the workspace). ACP evidence
consists of `tool_call` / `tool_call_update` notifications, permission requests,
terminal events and streamed `agent_message_chunk` / `agent_thought_chunk` text.
File effects are captured by ABB's workspace file evidence, and model traffic by
the interceptor.

## Known behavior

- `save_memory` writes to `.llxprt/LLXPRT.md` in the Case workspace by default
  (`scope = "global"` writes to the disposable config directory), so a memory
  note shows up as a workspace change and nothing persists across Cases.
- With the empty models.dev catalog LLxprt does not know the selected model's
  context window or prices; it neither reports a cost nor compresses history based
  on that window.
- The `llxprt` bin keeps a small Node parent process that forwards signals to the
  Bun child running the agent.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

The acceptance record describes one shared provider/model combination. It does not
certify every shared provider/model combination; run a fresh Case after changing it.

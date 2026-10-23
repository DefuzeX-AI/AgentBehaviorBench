# Open Interpreter ACP deployment

This unit installs the pinned [Open Interpreter](https://github.com/openinterpreter/openinterpreter)
release `0.0.45` (tag `rust-v0.0.45`, commit `d9b49c82`, Apache-2.0) — the Rust
CLI derived from OpenAI Codex — as the upstream prebuilt Linux package and runs
its built-in ACP server (`interpreter acp`, documented in upstream `docs/acp.md`).
ABB invokes it over ACP stdio and keeps each Case in a separate empty workspace.
No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

The runtime admits the exact `POST <selected-base>/chat/completions` route.

## Distribution

`install/distribution.json` pins
`open-interpreter-package-x86_64-unknown-linux-musl.tar.gz` from the
`rust-v0.0.45` GitHub release by sha256 (`9312213f…a0a087`). This is the same
package the upstream installer (`scripts/install/install.sh`) downloads. The
Dockerfile downloads it, checks it with `sha256sum -c`, and unpacks it to
`/opt/open-interpreter` (`bin/interpreter`, bundled `rg`, `bwrap` and `zsh`).
The binaries are statically linked against musl.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment) and prepares, for every Case, a disposable `HOME` and
`INTERPRETER_HOME` under `/var/lib/abb-open-interpreter` (mode 1777 in the
image). Upstream refuses to create its per-session `apply_patch` helper aliases
under the system temp dir, so this home cannot live in `/tmp`; it is still
writable by whichever unprivileged uid the runtime chooses and is discarded
with the container.

It writes `config.toml` with:

- a Chat Completions provider `abb_shared` (`base_url = $ABB_AGENT_MODEL_BASE_URL`,
  `env_key = "ABB_AGENT_MODEL_API_KEY"` — the key stays in the environment, not the file,
  `wire_api = "chat"`); the chat wire posts to `<base>/chat/completions`, which is
  exactly the admitted route. `model = $ABB_AGENT_MODEL`, with a conservative 128000-token context budget;
- `web_search = "disabled"` and `check_for_update_on_startup = false`;
- `[analytics] enabled = false`, `[feedback] enabled = false`;
- `[features]` disabling features that are on by default in this build and reach
  hosted OpenAI/ChatGPT services or unprovisioned hosted tools: `plugins`,
  `remote_plugin`, `plugin_sharing`, `apps`, `tool_suggest`, `browser_use`,
  `computer_use`, `image_generation`, `in_app_updates`. With `plugins` on, session
  start syncs the curated plugin marketplace from `chatgpt.com/backend-api/plugins/*`,
  `api.github.com/repos/openai/plugins` and `git ls-remote github.com/openai/plugins`;
  the interceptor rejected the trace as `egress_denied` until these were disabled.
  (Upstream `docs/config-reference.md` lists `apps`/`plugins` as off by default;
  `codex-rs/features/src/lib.rs` at the pinned tag enables both.);
- `allow_login_shell = false`: Debian's `/etc/profile` resets `PATH` for login
  shells, which drops the helper directory carrying `apply_patch`; the model then
  spends turns hunting for the tool. Shell tools run as `bash -c` instead.

### ACP relay adaptations

The launcher runs `interpreter acp` as a child process and relays ACP stdio line
by line with two narrow adaptations; every other message passes through unchanged.

1. **Session mode.** `interpreter acp` starts each session in `workspace-write`
   mode, which runs commands and patches inside its bubblewrap sandbox. ABB's
   container policy (`--cap-drop=ALL`, `no-new-privileges`) does not allow
   unprivileged user namespaces, so bubblewrap fails with
   `No permissions to create a new namespace` and every command and file change
   fails before running (the legacy Landlock backend panics on the same profile).
   The container is the isolation boundary here, so the launcher selects the
   upstream `full-access` mode: it holds the `session/new` response, sends
   `session/set_mode` (`full-access`) to the agent, swallows that reply and then
   returns the held response with `currentModeId = "full-access"`. In that mode
   upstream uses approval policy `never`, so no `session/request_permission`
   calls are made; tool calls are still reported as ACP `tool_call` updates.
2. **Duplicate message replay.** The pinned ACP server
   (`codex-rs/acp-server/src/lib.rs`, `handle_notification`) streams every
   message delta as `agent_message_chunk` and then, on `ItemCompleted`, sends the
   whole message text again as one more `agent_message_chunk` (same for reasoning
   as `agent_thought_chunk`). ACP clients concatenate chunks, so every reply
   appeared twice in the Case output. The relay drops a chunk whose text equals
   everything streamed since the previous boundary (prompt start, tool call, or
   the previous replay); nothing else is changed.

## Known behavior

- The workspace directory is created mode `0777` so it is writable by whichever
  unprivileged uid the runtime selects.
- The bundled model catalog logs `Unknown model … fallback model metadata` warnings
  were observed with GLM during previous acceptance; each new provider/model combination needs fresh validation.
- When the model endpoint returns an error (e.g. GLM `1302` rate limiting in previous acceptance), the
  ACP turn still ends with `end_turn` and an empty reply rather than an error.
- Open Interpreter's system prompt advertises capabilities (web search, MCP,
  plugins, subagents); web search, plugins and apps are disabled, no MCP server is
  configured, and requests beyond the model route are blocked.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Earlier acceptance records describe the previous fixed-provider deployment. They do not
certify every shared provider/model combination; run a fresh Case after changing it.

# Easy Code ACP deployment

This unit installs the pinned [Easy Code](https://github.com/OrionStarAI/EasyCode)
CLI release, npm package `easycode-ai@1.1.91` (formerly DeepV Code), and runs its
built-in ACP server (`easycode --acp`). ABB invokes it over ACP stdio and keeps each
Case in a separate empty workspace. No upstream source is vendored or modified.
Easy Code is a fork of Google's Gemini CLI.

The recorded revision `3e7d8e89` is the `gitHead` npm records for 1.1.91 (also in the
package's `bundle/build-info.json`). That commit is not on the public repository:
its `opensource` branch ends at `887b8bb4` (2026-06-18, CLI 1.1.14) while npm
releases continue. The installed artifact is the integrity-pinned npm tarball.

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

Easy Code's built-in models are served only through its own server
(`api-code.deepvlab.ai`) and need an Easy Code account. A *custom* model is called
directly: its `openai` provider posts to `<baseUrl>/chat/completions`, the exact
route the runtime admits. The launcher configures the selected model as the only
custom model and makes it the preferred model, so no Easy Code account is used.

## Distribution

`install/` pins `easycode-ai@1.1.91` in `package.json` and `package-lock.json`
(29 packages, all with registry integrity). The package is a prebuilt bundle with
no install scripts and requires Node >= 22.20; the image uses `node:24-bookworm`,
installs with `npm ci` and checks `easycode --version`.

## Launcher behavior

For every Case `bootstrap/launch.py` validates the three variables, creates a
disposable `HOME` under `/tmp` and writes:

- `~/.easycode-user/custom-models.json` with one entry: `displayName` `abb`,
  `provider` `openai`, `baseUrl` from `ABB_AGENT_MODEL_BASE_URL`, `modelId` from
  `ABB_AGENT_MODEL` and the key. Easy Code reads a custom model's key only from this
  file (it has no environment reference), so the file is created with `O_EXCL` and
  mode `0600` inside the disposable `HOME`, as in `26-kode-cli` and `29-mastracode`.
  The key is not passed in argv or in Easy Code's environment.
- `~/.easycode-user/settings.json` with `preferredModel = "custom:abb"`. Without it
  a session starts on `auto`, which only Easy Code's server can serve.

It then `exec`s `node .../easycode-ai/bundle/easycode.js --acp`. With `--acp`,
Easy Code sends its console logging to stderr, so stdout carries only JSON-RPC.
The launcher drops inherited variables that would select another auth type, web
URL, settings or model file, host integration or Google credential.

## Tools and permissions

ACP `initialize` advertises one auth method, `proxy-auth`, and `session/new`
succeeds without calling it. Easy Code logs that no stored Easy Code credential
exists and continues. Tools run without ACP permission requests, except
`ask_user_question`, which is sent as `session/request_permission` with the
questions in `_meta.dvcode.askUserQuestion`. ABB's `allow_once` policy approves it,
so the call completes instead of waiting for a human.

The model is offered 43 tools. These were each called once from a stub model with
all non-loopback connections refused; the result decides how they are described in
`requirement.md`:

| Tool | Result in this deployment |
|---|---|
| `google_web_search`, `web_fetch` | Report themselves unavailable: they need a custom Gemini Flash model. No request is made. |
| `image_reader` | Reports itself unavailable: no vision-capable custom model. |
| `lint_fix` | Fails: requires the Easy Code VS Code extension. |
| `search_skill_marketplace` | Fails: `skills.deepvlab.ai` is refused. `get_skill_marketplace_detail` and `install_skill` use the same store. |
| `ppt_outline` / `ppt_generate` | The outline is kept locally; generation submits it to Easy Code's server and opens a browser, neither available. |
| `opencli` | Reports that OpenCLI is not installed. |
| `lark_cli`, `lark_doc`, `lark_mail` | No Lark/Feishu account. Without a `lark-cli` binary, `lark_cli` runs `npx -y @larksuite/cli@latest`, an unpinned download through the egress observer. |
| `run_shell_command`, `write_file`, `local_time`, `lsp` | Work locally (no language server is installed, so `lsp` returns no results). |

Easy Code also sends two vendor extension requests, `_dvcode/host/turnToken` and
`_dvcode/host/checkpointCreated`. A client that answers "method not found" does
not interrupt the turn. File-edit checkpoints are Git commits kept under the
disposable `HOME`, not in the workspace.

## Known behavior

- On the first prompt of a session Easy Code makes one additional model call, with
  no tools, to title the session. It then sends the title as an ordinary
  `agent_message_chunk` with the text `[TITLE_UPDATE] <title>`, so the first step's
  output can contain that line. No setting disables it. The Agent Profile states
  that this line is not part of the answer.
- At session start Easy Code requests its cloud model list
  (`GET https://api-code.deepvlab.ai/web-api/models`). ABB's egress observer refuses
  and records it; Easy Code logs `model-list preload failed` and uses the custom model.

## Installation inputs

`install/package.json` and `install/package-lock.json` are applied into the ignored
`agent/` directory by source preparation; `agent/` is never committed.

## Validation scope

Verified locally with the pinned 1.1.91 package on Node 24.22.1, with all
non-loopback connections refused and a stub OpenAI-compatible model: ACP
initialize, `session/new` with the custom model current, a completed
`session/prompt` (`end_turn`), the tool results above, and the single refused
startup request; the only connections that went through were to the stub model. A
containerized Local Smoke with a real provider and KUMA evaluation are tracked in
the onboarding issue.

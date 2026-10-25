# Moltis ACP deployment

This unit installs the pinned [Moltis](https://github.com/moltis-org/moltis) release
`20261023.01` as its official prebuilt Linux binary and runs its built-in headless
ACP server (`moltis acp`, `crates/cli/src/acp_backend.rs`, documented in
`docs/src/acp-server.md`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

The recorded source revision `177f8f13` is the commit of tag `20261023.01`, from
which upstream CI built the release binaries. `agent add` imported the default branch
on 2026-10-25 at `8a12400d`; the snapshot and the recorded revision were reset to the
tag so that they describe the deployed binary.

## Licence

MIT (`LICENSE.md`). The unit only downloads the unmodified release archive at build
time.

## Model provider

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

Moltis's custom OpenAI-compatible provider with `wire_api = "chat-completions"` posts
to `<base_url>/chat/completions`, which is the exact route the runtime admits. With
`fetch_models = false` and a fixed model list it makes no catalog request. Its HTTP
client (reqwest with rustls) accepts the runtime's interception certificate as
provided by the `pem-env` trust plugin: in the acceptance run every model request
reached the interceptor and returned 200, so no loopback relay is needed.

## Installation

`install/distribution.json` pins, for `aarch64` and `x86_64`, the release archive
`moltis-20261023.01-<arch>-unknown-linux-gnu.tar.gz` and the SHA-256 published next to
each asset (`<asset>.sha256`). The Dockerfile selects the entry for `uname -m`,
verifies the download with `sha256sum -c`, installs `moltis` to `/opt/moltis/bin`
and its `share/moltis` assets (WASM tools, web assets) to `/opt/moltis/share/moltis`
(`MOLTIS_SHARE_DIR`), and runs `moltis --version`. The binary requires glibc 2.39 and
libgomp, so the image is `python:3.12-slim-trixie` plus `libgomp1` and
`ca-certificates`. A source build of the 59-crate Rust workspace is not used: it
would need a full Rust toolchain and far more memory than the binary download, and
would not change the deployed program.

`ripgrep`, `git` and `curl` are installed from Debian for the agent's shell commands.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment), creates a disposable directory under `/tmp` for every Case and `exec`s
`/opt/moltis/bin/moltis acp --config-dir <tmp>/config --data-dir <tmp>/data`, which
owns the ACP stdio channel directly. Config, `defaults.toml`, databases, sessions,
memory, the code index and logs therefore stay out of the Case workspace and are
writable by whichever unprivileged uid the runtime chooses; `XDG_*` directories point
into the same root. It writes one `moltis.toml`:

- `[providers] offered = ["custom-abb"]` and one `[providers.custom-abb]` with
  `base_url` = `ABB_AGENT_MODEL_BASE_URL`, `models = [ABB_AGENT_MODEL]`,
  `wire_api = "chat-completions"`, `fetch_models = false` and
  `api_key = "${ABB_AGENT_MODEL_API_KEY}"`. Moltis substitutes `${VAR}` from the
  environment when it loads the file (`crates/config/src/loader/config_io.rs`), so
  the key never appears in argv or on disk. It is the only provider and model.
- `[tools.exec.sandbox] mode = "off"` and `[tools.exec] approval_mode = "off"`
  (see below).

The launcher removes native provider, embedding, web search and remote-sandbox keys
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`,
`BRAVE_API_KEY`, `VERCEL_TOKEN`, `DAYTONA_API_KEY` and others) from the child
environment so the built-in providers and remote sandboxes stay unused.

## Tools, sandbox and approvals

The model is offered 68 tools, including `Read`, `Write`, `Edit`, `MultiEdit`,
`Glob`, `Grep`, `exec`, `process`, `calc`, `task_list`, `memory_*`, `codebase_*`,
checkpoints, `spawn_agent`, `sessions_*`, `cron`, `mcp_*`, `web_fetch`, `browser`
and messaging, voice and connector tools. Moltis runs every tool itself; it does not
use ACP client file-system methods or terminals, and it reports tool calls as
`tool_call` / `tool_call_update` without asking the client.

Two settings depart from the upstream defaults because they cannot work in a headless
ACP container:

- **Sandbox mode.** The default is `mode = "all"` with `backend = "auto"`. There is
  no Podman, Docker or Apple Container runtime inside the Agent image, so
  auto-detection (`crates/tools/src/sandbox/router.rs`) falls back to the
  restricted-host backend, whose path check (`check_restricted_host_path`,
  `crates/tools/src/sandbox/platform.rs`) admits only the data directory and `/tmp`.
  A local probe showed every `Write` to the session cwd rejected ("outside the
  allowed directories") and the model moving the file to `/tmp`. The Agent
  container is the isolation boundary here, so the unit uses the documented
  `mode = "off"`: tools run directly in the container, in the session cwd.
- **Approval mode.** The default `approval_mode = "on-miss"` asks an operator before
  any command outside Moltis's safe-bin list. `docs/src/acp-server.md` states that
  `session/request_permission` is not yet routed through Moltis's tool gate, so
  nobody can answer: a local probe showed `python3 hello.py` waiting for the 120 s
  approval timeout and failing with "approval timed out". The unit uses the
  documented headless value `approval_mode = "off"`; Moltis still denies its built-in
  dangerous command patterns in this mode (`crates/tools/src/approval.rs`).
  `permission_policy = "allow_once"` only answers a permission request if one ever
  arrives.

With `mode = "off"`, the `process` tool (tmux sessions) starts in `/home/sandbox`,
which does not exist in this image, and fails. `requirement.md` lists it and the tools
that have no backing service in this deployment.

## Model compatibility

With `doubao-seed-2-1-lite-260915` on Volcengine Ark, three local probes produced
invalid `exec` arguments in the model's own streamed tool call
(`{"command": "...", "timeout": 10, "working_dir": /work}`, recorded raw from the
SSE stream), which Moltis correctly rejects before execution. The acceptance run
uses DeepSeek (`ABB_MODEL_PROVIDER=deepseek`), whose tool calls are well formed.

## Known non-blocking noise

At startup Moltis logs a warning that the optional `dcg` destructive-command guard
is not on `PATH`, and that no embedding provider is configured (memory uses keyword
search only). Both are upstream optional components and do not affect a Case.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

The acceptance record describes one shared provider/model combination. It does not
certify every shared provider/model combination; run a fresh Case after changing it.

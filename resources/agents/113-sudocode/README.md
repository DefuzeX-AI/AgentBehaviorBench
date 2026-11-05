# Sudo Code ACP deployment

This unit installs the pinned [Sudo Code](https://github.com/sudoprivacy/sudocode)
release `v0.2.36` (`scode`) as its official prebuilt Linux binary and runs its
built-in ACP stdio server (`scode acp`, `rust/crates/engine-acp`). ABB invokes it
over ACP stdio and keeps each Case in a separate empty workspace. No upstream source
is vendored or modified.

The recorded source revision `e8206667` is the commit of tag `v0.2.36`; the release
binary reports the same Git SHA (`scode version`). `agent add` imported the default
branch on 2026-10-25 at `5d48e9fb`, 138 commits past the tag; the snapshot and the
recorded revision were reset to the tag so that they describe the deployed binary.

## Licence

MIT (`LICENSE` in the repository). The unit only downloads the unmodified release
archive at build time.

## Model provider

This unit uses default model selection; no provider pin is declared. Configure the
selected provider in `.env`: OpenRouter -> DeepSeek -> GLM, choosing the first
nonempty API key, or set `ABB_MODEL_PROVIDER` explicitly. Supply the selected
provider's model name as well. See [model selection](../../../docs/Model-Selection.md)
for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

scode refreshes its model catalog with `GET <base_url>/models` (context window,
output ceiling, tool support; `docs/models.md`, "Automatic discovery"), so
`agent.toml` declares `[model] metadata_paths = ["/models"]`. The only other model
route is `POST <base_url>/chat/completions`.

## Installation

`install/distribution.json` pins, for `aarch64` and `x86_64`, the release archives
`scode-linux-arm64.tar.gz` and `scode-linux-x64.tar.gz` and their SHA-256 as published
in the release's `SHA256SUMS.txt`. The Dockerfile selects the entry for `uname -m`,
verifies the download with `sha256sum -c`, extracts only the `scode` member to
`/opt/scode/bin` and runs `scode --version`. The binary needs only glibc, libm and
libgcc_s, so the image is `python:3.12-slim-bookworm` plus `ca-certificates`. A source
build of the Rust workspace is not used: it would need a full Rust toolchain and far
more memory than the binary download, and would not change the deployed program.

`ripgrep` and `git` are installed from Debian for the agent's shell commands.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query or
fragment) and creates a disposable directory under `/tmp` for every Case. It writes a
`sudocode.json` there, selected with `SCODE_GLOBAL_CONFIG_DIR`, with one api-key
connection `abb` (`baseUrl` = the model relay below, `apiKeyEnv =
"ABB_AGENT_MODEL_API_KEY"`) and one model alias `abb` mapped to the selected model ID
with `api = "openai-completions"`. scode reads the key from the environment at
request time, so it never appears in argv or on disk.

`SCODE_PROJECT_CONFIG_DIR` points at an absolute directory in the same disposable
root, so the project config layer, the agent memory directory scode derives from it
and the catalog cache stay outside the Case workspace, and a Case cannot redirect the
provider by writing `<workspace>/.nexus/sudocode/sudocode.json`. `SCODE_LOG_PATH`
keeps scode's log there too. `SCODE_CHECK_UPDATES=0` disables release checks (they
only run in interactive terminals anyway); telemetry is opt-in and not enabled.
Native provider, proxy, Nexus and web-search variables (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `PROXY_AUTH_TOKEN`, `NEXUS_API_KEY` and others) are removed from
the child environment.

It then runs `/opt/scode/bin/scode --model abb --auth api-key --permission-mode
workspace-write acp` as a child process that owns the ACP stdio channel.

### Model relay

scode's HTTP client is reqwest with `rustls-tls`, which trusts only its bundled
webpki roots and ignores `SSL_CERT_FILE`, so it cannot verify the runtime's model
interceptor; the first smoke failed with `invalid peer certificate: UnknownIssuer`
and no intercepted request. As in `81-aster`, `bootstrap/model_relay.py` serves plain
HTTP on an ephemeral `127.0.0.1` port (added to `NO_PROXY`) and the `abb` connection
points at it. The relay sends the same method, path, body and
`Authorization`/`Content-Type`/`Accept`/`User-Agent`/`X-Request-Id` headers to the
selected HTTPS base URL with Python's default TLS context (which honours
`SSL_CERT_FILE`) through the runtime's `HTTPS_PROXY`, and streams the response
(including SSE and error statuses) back unchanged. Every model request is still
intercepted and recorded by the runtime. Only `POST /chat/completions` and
`GET /models` are relayed; anything else gets a local 404.

## Tools and permissions

Over ACP the model is offered `read_file`, `write_file`, `edit_file`, `glob_search`,
`grep_search`, `bash`, `TodoWrite`, `write_plan`, `AskUserQuestion`, `agent_spawn`,
`pid_fork`, `pid_output`, `pid_status`, `pid_kill`, `agent_list`, `send`, `Monitor`,
`Sleep`, `CronCreate`, `CronList`, `CronDelete`, `Config`, `Skill`, `ToolSearch`,
`StructuredOutput`, `read_tool_output`, `set_tip`, `PowerShell`, `WebFetch` and
`WebSearch` (some are deferred behind `ToolSearch`). File tools write directly in the
container and `bash` runs locally; scode uses neither ACP client terminals nor client
file-system methods. No web search provider, MCP server or connector is configured,
and `WebFetch`/`WebSearch` have no admitted route.

The session runs in scode's documented `workspace-write` permission mode
(`docs/permissions-and-sandbox.md`), so the ACP client is the approval gate: shell
commands send `session/request_permission`, which ABB answers with its `allow_once`
policy. An offline check answering `reject_once` fails the tool with `user selected:
reject_once`. The upstream default, `danger-full-access`, would run every tool
without asking.

## Known non-blocking noise

scode stores each ACP session under `<workspace>/.scode/sessions/<fingerprint>/`
(transcript, writer locks and compressed raw response recordings, which exclude
authorization headers; `rust/crates/runtime/src/session_control.rs`). There is no
option to move it. When workspace file evidence is collected these files appear in
it; they are upstream behaviour, not changes the task asked for.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

The acceptance record describes one shared provider/model combination. It does not
certify every shared provider/model combination; run a fresh Case after changing it.

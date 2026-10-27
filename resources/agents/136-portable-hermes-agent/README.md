# Portable Hermes Agent ACP deployment

This unit installs the pinned [Portable Hermes Agent](https://github.com/aivrar/portable-hermes-agent)
release `v1.4.17` (commit `26462e29`, `hermes-agent` 0.20.6, MIT license) and runs its
built-in ACP adapter (`hermes acp`, equivalent to `hermes-acp` /
`python -m acp_adapter`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

Portable Hermes Agent is a Windows *distribution* of the Hermes Agent core: the
repository carries the full Python project (`pyproject.toml`, `uv.lock`,
`acp_adapter/`, `tools/`, `agent/`) plus Windows launchers (`START.bat`,
`install.bat`), a Tkinter GUI and portable service integrations (LM Studio, TTS,
Music, ComfyUI). Only the Python core is installed here; the launchers, the GUI
and the embedded Python/Node.js runtime are not part of the evaluated surface,
and the portable service tools are not reachable over ACP (see
[Toolset surface](#toolset-surface)).

This unit uses default model selection; no `[model] provider` declaration is needed.
Configure the selected provider in `.env`: OpenRouter -> DeepSeek -> GLM, choosing
the first nonempty API key, or set `ABB_MODEL_PROVIDER` explicitly. Supply the
selected provider's model name as well. See
[model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER`
variables. Users do not fill these internal variables. Only the selected credential
reaches the launcher. The runtime derives the exact observed model route from the
selected URL.

## How it is installed

`install/distribution.json` pins the repository, tag and commit. The image clones
that tag with `--depth 1 --single-branch`, fails the build unless `git rev-parse HEAD`
equals the pinned commit, and runs `uv sync --frozen --no-dev --extra acp --extra
bedrock --extra vertex` against the project's own `uv.lock` into `/opt/hermes/.venv`
(separate from the ABB runtime venv `/opt/venv`). `uv` itself is the hash-locked
0.11.6 release the project's own Dockerfile pins. The build ends with three
assertions: `tirith --version`, `hermes --version` and `hermes acp --check`, so a
broken adapter cannot produce a passing image.

Why not the other channels:

- The release assets are the Windows portable ZIP and a PDF manual; there is no
  Linux binary, so a sha256-pinned executable download is not available.
- PyPI carries `hermes-agent` 0.19.0, behind this tag, and the portable release
  is not published there.
- The project's own image is ~1 GB and bundles Playwright/Chromium, ffmpeg,
  docker-cli, a built SQLite, a Node 26 runtime, the `web`/`ui-tui` frontends and
  an s6-overlay PID 1 entrypoint for its gateway/dashboard services. None of that
  is used over ACP, and it would need its entrypoint, user and `HERMES_HOME`
  volume overridden.
- `uv sync --frozen` against the checked-in `uv.lock` is the install the project
  itself uses, so the dependency set is exactly the reviewed one.

## Toolset surface

The ACP session selects the project's `hermes-acp` toolset
(`toolsets.py:532-550`) — the coding-focused selection built for editor
integrations. It contains file, terminal, process, code-execution, delegation,
todo, memory, session-search, vision, skill and browser tools, plus
`web_search`/`web_extract`.

It does **not** contain the portable-only toolsets (`lm_studio`, `music`, `tts`,
`comfyui`, `workflow`, `tool_maker`, `serper`, `gpu`, `guide`, `hermes_update`),
which are registered in `toolsets.py:198-282` and surfaced by the Windows GUI.
Those tools are additionally hidden by their own `check_fn` until a matching
local server answers (`tools/lm_studio_tools.py:888-937`, `tools/gpu_tool.py:77`,
`tools/serper_search_tool.py:151`; a `check_fn` that fails is honoured and the
dependent tools become unavailable for that turn, `tools/registry.py:399-417`).
So no GPU, LM Studio, ComfyUI, TTS or Music backend is advertised in a Case, and
nothing attempts to auto-install one.

## Launcher behavior

`bootstrap/launch.py` validates the three model variables, then for every Case
creates a disposable `HOME` under `/tmp` with `HERMES_HOME=$HOME/.hermes` (the
container may run as a uid that cannot write `/home/agent`; this also isolates
the SQLite session store, memories and logs per Case). It writes
`$HERMES_HOME/config.yaml` and execs `hermes acp`. The key stays in the
environment: the config references it as `${ABB_AGENT_MODEL_API_KEY}`, which
`hermes_cli/config.py:_expand_env_vars` (:2778-2792) resolves from the process
environment, so no plaintext credential lands on disk.

### Why config.yaml and not OPENAI_BASE_URL

This is the one place where this release differs materially from the upstream
`20-hermes-agent` unit, which pins `hermes-agent` 0.21.5. In 0.20.6:

- `hermes_cli/runtime_provider.py:1392-1393` states that the `OPENAI_BASE_URL`
  env var "is no longer consulted — config.yaml is the single source of truth for
  endpoint URLs".
- `:1447-1458` host-gates `OPENAI_API_KEY` to `openai.com` / `openai.azure.com`,
  so an OpenRouter, DeepSeek or GLM endpoint would resolve to *no* credential at
  all (the same host-gating added for #28660 / GHSA-76xc-57q6-vm5m).
- `openai-api`'s overlay declares `transport="codex_responses"`
  (`hermes_cli/providers.py:68-72`), which resolves to the Responses wire shape.

The launcher therefore writes the endpoint into `model:` with
`provider: "custom"` — the documented id for "any other OpenAI-compatible
endpoint" (`cli-config.yaml.example:73-74`), and the one provider whose configured
`base_url` is trusted unconditionally
(`_config_base_url_trustworthy_for_bare_custom`, `:110-111`), which also makes the
config-supplied `api_key` usable (`:1449`). It pins
`model.api_mode: "chat_completions"`, honoured for bare `custom` by
`_resolve_plain_custom_api_mode` (`:221-232`) and valid per `_VALID_API_MODES`
(`:430-441`).

That pin is load-bearing: ABB's shared interception admits exactly
`POST <selected-base>/chat/completions`
(`agentbench/runtime/interception/native_model.py:82-92,107`). Without it a
`codex_responses` overlay would send the turn to `/responses`, which the egress
observer would record as undeclared traffic.

The remaining settings switch off calls outside the evaluated model route:

- `model_catalog.enabled: false` stops the remote Nous model catalog fetch
  (`hermes-agent.nousresearch.com`);
- `models_dev.url` is set to a `file://` URL. `models_dev.url` is read at
  `agent/models_dev.py:292`; `requests` has no adapter for that scheme, so the
  fetch fails locally without opening a socket and Hermes falls back to its
  bundled provider data. (A closed loopback port does not work here: the runtime
  redirects loopback TCP to the interceptor too, which would reject it as
  undeclared egress.);
- `model_catalog.excluded_providers` drops the keyless OpenCode relays
  (`opencode-free`, `opencode-zen`, `opencode-go`). They otherwise appear in the
  ACP session model picker, which fetches their catalog from `opencode.ai` at
  `session/new`;
- `auxiliary.title_generation.enabled` and `auxiliary.background_review.enabled`
  are off: both start an extra model call after a turn, which the one-shot worker
  interrupts when it closes ACP. Both keys exist in this release's
  `DEFAULT_CONFIG` (`hermes_cli/config_defaults.py:1212`, `:1334`) and
  `background_review.py:281` reads the enabled flag;
- `curator.enabled` is off. There is deliberately **no `updates.check`** entry:
  that key does not exist in 0.20.6, where update checks are the `hermes update`
  CLI and the `hermes_update` toolset, which the ACP toolset does not include.
  As in upstream's image, `HERMES_DISABLE_LAZY_INSTALLS=1` keeps the venv sealed
  while `HERMES_LAZY_INSTALL_TARGET` (a per-Case temp dir) lets optional backends
  such as PDF/DOCX readers install on demand (`tools/lazy_deps.py:537,1064`); the
  venv gets `pip` at build time (the image removes `uv`). PyPI is on the egress
  observer's default allowlist.

Two further env vars keep startup off the network:
`HERMES_ACP_SKIP_CONFIGURED_MCP=1` skips MCP discovery (`acp_adapter/entry.py:260`),
and `HERMES_SKIP_NODE_BOOTSTRAP=1` suppresses the portable Node.js bootstrap that
the GUI/TUI surfaces use (`hermes_cli/main.py:2392-2396`).

The interception manifest admits one model route:
`POST <selected-base>/chat/completions`.

`[model] metadata_paths` adds one optional metadata route at runtime,
`GET <selected-base>/models` (exact path, GET only, `required = false`). The ACP
session model picker lists the configured provider's live models at `session/new`
(`acp_adapter/server.py:100`), and per-turn cost estimation reads pricing from the
same endpoint (`agent/model_metadata.py:1350`). Both fall back to bundled data when
the call fails, so the route is not needed for a turn to complete; it is admitted so
the trace is not rejected over read-only catalog metadata.

The exact model and metadata routes follow the resolved provider URL.

## Known non-blocking noise

- `hermes_state: state.db: linked SQLite ... is vulnerable to the WAL-reset
  corruption bug ... using journal_mode=DELETE`. Debian bookworm's SQLite is older
  than the version upstream compiles; Hermes detects this and uses rollback-journal
  mode for its session store instead of WAL. Upstream's own image builds a newer
  SQLite; that is not replicated here because the store is per-Case and
  single-process.
- `tools.registry: check_fn ... returned False` for connector and similar
  toolsets: no connector backend is provisioned, so Hermes hides those tools.
  This is the intended path for the portable service toolsets described above.
- The browser toolset is available: the image installs Debian's Chromium and the
  `agent-browser` CLI this release pins
  (`tools/browser_tool.py` `AGENT_BROWSER_NPX_SPEC = "agent-browser@^0.26.0"`),
  `launch.py` starts one headless Chromium per Case on `127.0.0.1:9222` (a declared
  loopback route) and points Hermes at it with `BROWSER_CDP_URL`
  (`tools/browser_tool.py:567`). `abb-chromium` trusts the interceptor CA
  (Chromium ignores `SSL_CERT_FILE`); `zz-abb-lean` keeps Chromium within the
  128-pid budget (#158).

## tirith command scanner

Hermes scans every terminal command with [tirith](https://github.com/sheeki03/tirith)
before running it (`tools/tirith_security.py`), and when the binary is missing it
downloads the latest release from GitHub on the first terminal command. Inside ABB
that download is undeclared egress, so the host rejected the trace. The image
installs the pinned release recorded in `install/tirith.json` (v0.4.2,
sha256-verified; tirith is AGPL-3.0 and is fetched at build time, not vendored),
and the launcher sets `security.tirith_path` to it — an explicit path is
authoritative upstream and never falls through to auto-download
(`_is_explicit_path` -> `_resolve_tirith_path`, `tirith_security.py:488-503`) —
plus `TIRITH_OFFLINE=1`, because `tirith check` otherwise refreshes its threat
database from GitHub. This release invokes the binary as
`tirith check --json --non-interactive` (`tirith_security.py:777`), which v0.4.2
provides. Scanning stays enabled: a `curl … | sh` command is still flagged as HIGH
risk and needs approval.

## Web tools

Hermes picks its web backend automatically (`tools/web_tools.py:_get_backend`) and
uses Tavily when `TAVILY_API_KEY` is set; the other backends need their own
credentials, none of which are provisioned. `TAVILY_API_KEY` is an optional secret
(`optional_secret_env_keys`); when it is supplied, `web_search` and `web_extract`
are offered and call `api.tavily.com` (`POST /search, /extract`), declared as a tool
route in `network/rules.toml`, so requests and results are forwarded and recorded as
tool evidence. Without the key the tools are not offered, as before. Other non-model
traffic goes to ABB's egress observer, which forwards allowlisted hosts (the package
registries by default), refuses the rest with 403 and records every attempt in
`egress.jsonl`; a refusal does not reject the Case (#137).

## Installation inputs

Tracked installation manifests live in `install/`. Before the evaluation SDK starts,
ABB prepares their copies in the ignored `agent/` directory
(`source.method = install`). Docker builds use those generated copies. Do not edit
`agent/`; edit `install/` instead. If an existing copy differs, move `agent/` aside
and rerun to regenerate it.

## Validation scope

This unit's acceptance record covers the pinned tag and the provider configured at
the time of the run. It does not certify every shared provider/model combination;
run a fresh Case after changing it.

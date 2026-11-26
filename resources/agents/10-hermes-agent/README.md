# Hermes Agent ACP deployment

This unit installs the pinned [Hermes Agent](https://github.com/NousResearch/hermes-agent)
release `0.21.5` (tag `v2026.9.24`, commit `f97608f1`, MIT license) and runs its
built-in ACP adapter (`hermes acp`, equivalent to `hermes-acp` /
`python -m acp_adapter`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

## How it is installed

`install/distribution.json` pins the repository, tag and commit. The image clones
that tag with `--depth 1`, fails the build unless `git rev-parse HEAD` equals the
pinned commit, and runs `uv sync --frozen --no-dev --extra acp` against upstream's
own `uv.lock` into `/opt/hermes/.venv` (separate from the ABB runtime venv
`/opt/venv`). `uv` itself is copied from the same digest-pinned
`ghcr.io/astral-sh/uv` image upstream's Dockerfile uses.

Why not the other channels:

- PyPI only carries `hermes-agent` 0.19.0, two releases behind; the npm package
  named `hermes-agent` is not published by Nous Research.
- Upstream deliberately blocks wheel/sdist builds (`setup.py` raises unless
  `HERMES_NIX_BUILD=1`), so `pip install git+...` fails. Setting that variable
  would bypass an upstream guard; `uv sync` with an editable project install is
  the supported source install and is exactly what upstream's own Dockerfile does.
- The official image `nousresearch/hermes-agent:v2026.9.24` (~1 GB compressed)
  bundles Playwright/Chromium, ffmpeg, docker-cli and an s6-overlay PID 1
  entrypoint for its gateway/dashboard services. None of that is used over ACP,
  and it would need its entrypoint, user and `HERMES_HOME` volume overridden.

## Launcher behavior

`bootstrap/launch.py` validates the three variables, then for every Case creates
a disposable `HOME` under `/tmp` with `HERMES_HOME=$HOME/.hermes` (the container
may run as a uid that cannot write `/home/agent`; this also isolates Hermes'
SQLite session store, memories and logs per Case). It writes
`$HERMES_HOME/config.yaml` and starts `hermes acp`. The key reaches Hermes only
through its native `OPENAI_API_KEY` variable, never argv or a file.

The config selects Hermes' built-in `openai-api` provider with `model.default=$ABB_AGENT_MODEL`
and `model.base_url=$ABB_AGENT_MODEL_BASE_URL`, also exported through Hermes' native
`OPENAI_BASE_URL` setting. The remaining settings
switch off calls outside the evaluated model route:

- `model_catalog.enabled: false` stops the remote Nous model catalog fetch
  (`hermes-agent.nousresearch.com`);
- `models_dev.url` is set to a `file://` URL. Hermes has no switch for its
  models.dev metadata fetch; `requests` has no adapter for that scheme, so the
  fetch fails locally without opening a socket and Hermes falls back to its
  bundled provider data. (A closed loopback port, as used in the host probe, does
  not work here: the runtime redirects loopback TCP to the interceptor too, which
  rejected it as undeclared egress.);
- `model_catalog.excluded_providers` drops the keyless OpenCode relays
  (`opencode-free`, `opencode-zen`, `opencode-go`). They otherwise appear in
  the ACP session model picker, which fetches their catalog from `opencode.ai`
  at `session/new`;
- `auxiliary.title_generation.enabled` and `auxiliary.background_review.enabled`
  are off: both start an extra model call after a turn, which the one-shot
  worker interrupts when it closes ACP;
- `curator.enabled` and `updates.check` are off. As in upstream's image,
  `HERMES_DISABLE_LAZY_INSTALLS=1` keeps the venv sealed while
  `HERMES_LAZY_INSTALL_TARGET` (a per-Case temp dir) lets optional backends such
  as PDF/DOCX readers install on demand; the venv gets `pip` at build time (the
  image removes `uv`). PyPI is on the egress observer's default allowlist.

The interception manifest admits one model route:
`POST <selected-base>/chat/completions`.

`[model] metadata_paths` adds one optional metadata route at runtime,
`GET <selected-base>/models` (exact path, GET only,
`required = false`). Hermes calls it at most twice per process and has no config
switch for either call at this tag: the ACP session model picker lists the
configured provider's live models at `session/new`, and per-turn cost estimation
reads pricing from the same endpoint. Both fall back to bundled data when the
call fails, so the route is not needed for a turn to complete; it is admitted so
the trace is not rejected over read-only catalog metadata.

The exact model and metadata routes follow the resolved provider URL.

## Known non-blocking noise

- `hermes_state: state.db: linked SQLite 3.40.1 ... is vulnerable to the
  WAL-reset corruption bug ... using journal_mode=DELETE`. Debian bookworm ships
  SQLite 3.40.1; Hermes detects it and uses rollback-journal mode for its session
  store instead of WAL. Upstream's own image compiles a newer SQLite; that is not
  replicated here because the store is per-Case and single-process.
- `tools.registry: check_fn ... returned False` for connector and similar
  toolsets: no connector backend is provisioned, so Hermes hides those tools.
  The browser toolset is available: the image installs Debian's Chromium and the
  `agent-browser` CLI Hermes pins, `launch.py` starts one headless Chromium per
  Case on `127.0.0.1:9222` (a declared loopback route) and points Hermes at it with
  `BROWSER_CDP_URL`. `abb-chromium` trusts the interceptor CA (Chromium ignores
  `SSL_CERT_FILE`); `zz-abb-lean` keeps Chromium within the 128-pid budget (#158). The ACP-visible toolset is the local file, search, terminal
  and code-execution tools.
- `Background MCP discovery previously exited with no connected servers`: no MCP
  servers are configured.

## tirith command scanner

Hermes scans every terminal command with [tirith](https://github.com/sheeki03/tirith)
before running it, and when the binary is missing it downloads the latest release
from GitHub on the first terminal command. Inside ABB that download is undeclared
egress, so the host rejected the trace. The image installs the pinned release
recorded in `install/tirith.json` (v0.4.2, sha256-verified; tirith is AGPL-3.0 and is
fetched at build time, not vendored), and the launcher sets
`security.tirith_path` to it — upstream treats an explicit path as authoritative and
never auto-downloads — plus `TIRITH_OFFLINE=1`, because `tirith check` otherwise
refreshes its threat database from GitHub. Scanning stays enabled: a
`curl … | sh` command is still flagged as HIGH risk and needs approval.

## Web tools

Hermes picks its web backend automatically (`tools/web_tools.py`) and uses Tavily when `TAVILY_API_KEY` is set; `ddgs` is not installed. `TAVILY_API_KEY` is an optional secret (`optional_secret_env_keys`); when it is
supplied, `web_search` and `web_extract` are offered and call `api.tavily.com` (`POST /search, /extract`),
declared as a tool route in `network/rules.toml`, so requests and results are forwarded
and recorded as tool evidence. Without the key the tools are not offered, as before.
Other non-model traffic goes to ABB's egress observer, which forwards allowlisted hosts
(the package registries by default), refuses the rest with 403 and records every attempt
in `egress.jsonl`; a refusal does not reject the Case (#137).

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Earlier acceptance records describe the previous fixed-provider deployment. They do not
certify every shared provider/model combination; run a fresh Case after changing it.

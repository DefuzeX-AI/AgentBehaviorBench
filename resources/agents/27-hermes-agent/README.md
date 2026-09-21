# Hermes Agent ACP deployment

This unit installs the pinned [Hermes Agent](https://github.com/NousResearch/hermes-agent)
release `0.21.3` (tag `v2026.9.14`, commit `345cd2b0`, MIT license) and runs its
built-in ACP adapter (`hermes acp`, equivalent to `hermes-acp` /
`python -m acp_adapter`). ABB invokes it over ACP stdio and keeps each Case in a
separate empty workspace. No upstream source is vendored or modified.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

## How it is installed

`agent/distribution.json` pins the repository, tag and commit. The image clones
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
- The official image `nousresearch/hermes-agent:v2026.9.14` (~1 GB compressed)
  bundles Playwright/Chromium, ffmpeg, docker-cli and an s6-overlay PID 1
  entrypoint for its gateway/dashboard services. None of that is used over ACP,
  and it would need its entrypoint, user and `HERMES_HOME` volume overridden.

## Launcher behavior

`bootstrap/launch.py` validates the three variables, then for every Case creates
a disposable `HOME` under `/tmp` with `HERMES_HOME=$HOME/.hermes` (the container
may run as a uid that cannot write `/home/agent`; this also isolates Hermes'
SQLite session store, memories and logs per Case). It writes
`$HERMES_HOME/config.yaml` and starts `hermes acp`. The key reaches Hermes only
through its native `GLM_API_KEY` variable, never argv or a file.

The config selects Hermes' built-in `zai` provider with `model.default=$GLM_MODEL`
and `model.base_url=$GLM_API_BASE_URL` (also exported as `GLM_BASE_URL`, which
makes Hermes skip its Z.AI endpoint-detection probes). The remaining settings
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
- `curator.enabled` and `updates.check` are off; `HERMES_DISABLE_LAZY_INSTALLS=1`
  prevents runtime pip installs of optional backends.

The interception manifest admits one model route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.

`network/rules.toml` adds one optional metadata route,
`GET https://open.bigmodel.cn/api/coding/paas/v4/models` (exact path, GET only,
`required = false`). Hermes calls it at most twice per process and has no config
switch for either call at this tag: the ACP session model picker lists the
configured provider's live models at `session/new`, and per-turn cost estimation
reads pricing from the same endpoint. Both fall back to bundled data when the
call fails, so the route is not needed for a turn to complete; it is admitted so
the trace is not rejected over read-only catalog metadata.

A different provider needs an explicit reviewed route update; changing
environment variables alone does not broaden container egress.

## Known non-blocking noise

- `hermes_state: state.db: linked SQLite 3.40.1 ... is vulnerable to the
  WAL-reset corruption bug ... using journal_mode=DELETE`. Debian bookworm ships
  SQLite 3.40.1; Hermes detects it and uses rollback-journal mode for its session
  store instead of WAL. Upstream's own image compiles a newer SQLite; that is not
  replicated here because the store is per-Case and single-process.
- `tools.registry: check_fn ... returned False` for the browser, connector and
  similar toolsets: no browser or connector backend is provisioned, so Hermes
  hides those tools. The ACP-visible toolset is the local file, search, terminal
  and code-execution tools.
- `Background MCP discovery previously exited with no connected servers`: no MCP
  servers are configured.

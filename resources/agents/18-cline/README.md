# Cline CLI ACP deployment

This unit installs the pinned [Cline](https://github.com/cline/cline) CLI release
`3.0.62` (npm `cline@3.0.62`, tag `cli-v3.0.62`, commit `d718dd16`, Apache-2.0)
from npm and runs its built-in ACP server (`cline --acp`). ABB invokes it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

The npm package is a small Node.js resolver; the agent itself is the prebuilt
native binary in the optional dependency `@cline/cli-linux-x64@3.0.62`
(about 151 MB, Bun runtime embedded). Both are pinned with registry integrity in
`install/package-lock.json`.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

The interception manifest admits only the tested route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

## Launcher behavior

`agent/` holds only a `package.json` and `package-lock.json` that pin
`cline@3.0.62`; the image installs it with `npm ci`, so the registry tarball
integrity is checked and no upstream file is edited.

`bootstrap/launch.py` validates the three variables, creates a disposable `HOME`
under `/tmp` for every Case (Cline's settings, session database and logs must be
writable by whichever unprivileged uid the runtime chooses) and starts
`cline --acp`:

- **Provider.** It selects Cline's built-in `zhipuai-coding-plan` provider with
  `CLINE_PROVIDER` / `CLINE_MODEL`, and writes `~/.cline/data/settings/providers.json`
  (mode 0600, no key inside) whose `baseUrl` is `GLM_API_BASE_URL`, so the endpoint
  is taken from the runtime profile rather than the provider default. The generic
  `openai-compatible` provider was not used: in ACP mode it silently ran
  `gpt-4o` instead of the requested model.
- **Model check.** Cline replaces a model ID it does not know with the provider
  default (`glm-5.3-flash`) without an error. The launcher therefore rejects
  `GLM_MODEL` values that are not in the pinned 3.0.62 catalog for this provider.
- **Credential.** ACP `session/new` answers "Authentication required" unless
  `CLINE_API_KEY` is set; Cline then uses it as the selected provider's key. The
  launcher sets it from `GLM_API_KEY` in the child environment only (not argv,
  not a file).
- **Egress switches.** Upstream contacts `otel.cline.bot` (telemetry) and
  `data.cline.bot` (PostHog feature flags) at startup and may check npm for
  updates; the interceptor rejects all of these as undeclared egress. The launcher
  writes `~/.cline/data/settings/global-settings.json` with
  `telemetryOptOut: true` and `autoUpdateEnabled: false`, and sets
  `CLINE_NO_AUTO_UPDATE=1` and `DO_NOT_TRACK=1`.
- **`E2E_TEST=true` (undocumented).** No documented setting disables the
  feature-flag request. In the 3.0.62 binary `E2E_TEST` is read in exactly one
  place: it swaps the PostHog feature-flag client for a no-op provider, so flags
  keep their compiled-in defaults. It does not alter tools, prompts, approvals or
  model traffic. (`IS_TEST` has the same effect plus a test-only flag override, so
  it is not used.)

- **`CLINE_SESSION_BACKEND_MODE=local` (undocumented in the CLI README).** With
  the default `auto` backend, Cline looks for a shared background "hub" daemon by
  polling `http://127.0.0.1:25463/health` and would start one. Inside ABB that
  loopback request goes through the interceptor and is rejected as undeclared
  egress (the first smoke run was host-rejected on 68 such probes). `local`
  is one of the three values the 3.0.62 binary accepts (`local|hub|remote`) and
  keeps sessions in-process, so no daemon is contacted or spawned.

## Known non-blocking noise

Cline keeps its session index in a SQLite database under the disposable `HOME`;
it is discarded with the container.

Cline's bundled AI SDK prints `DeprecationWarning: AI SDK Warning
(zhipuai-coding-plan.chat / glm-5.1): Deprecated: "providerOptions key ..."` and
an "AI SDK Warning System" banner on stderr for each model call. They come from
the upstream provider wiring, do not affect requests, and appear only in ACP
stderr evidence. No background title or summary model calls were observed: every
recorded model request belongs to a prompt turn and completed before ACP closed.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

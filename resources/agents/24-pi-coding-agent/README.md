# Pi coding agent ACP deployment

This unit installs the pinned [Pi coding agent](https://github.com/earendil-works/pi)
release `0.86.1` (npm `@earendil-works/pi-coding-agent`, tag `v0.86.1`, commit
`13cbf77d`, MIT) together with the [pi-acp](https://github.com/svkozak/pi-acp) ACP
adapter release `0.0.33` (tag `v0.0.33`, commit `1bfcb394`, MIT). Pi has no built-in
ACP server; `pi-acp` speaks ACP over stdio and drives `pi --mode rpc` as a child
process. ABB invokes `pi-acp` over ACP stdio and keeps each Case in a separate empty
workspace. No upstream source is vendored or modified.

`agent.toml` `[source]` and `source-manifest.json` pin the Pi repository, the
evaluated agent. The adapter pin (`svkozak/pi-acp` @
`1bfcb394088ed879db8fd936b570bb626017f878`) is recorded here and in the npm lock.

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
`@earendil-works/pi-coding-agent@0.86.1` and `pi-acp@0.0.33`; the image installs
both with one `npm ci`, so registry tarball integrity is checked and no upstream
file is edited. `pi-acp` requires Pi >= 0.80.4 and Node 22+ (the image uses Node 24).

For every Case `bootstrap/launch.py` validates the three variables, creates a
disposable `HOME` under `/tmp` and writes Pi's native config there
(`~/.pi/agent`, also passed as `PI_CODING_AGENT_DIR`, files mode 0600):

- `models.json` declares a custom `glm` provider with `api: openai-completions`,
  the base URL, and one model `$GLM_MODEL` (`reasoning: true`, 200k context,
  32k max output). `apiKey` is the literal string `"$GLM_API_KEY"`, which Pi
  resolves from the environment at request time, so the credential never touches
  disk or argv. `compat.supportsDeveloperRole: false` keeps the system prompt in
  the `system` role (GLM does not accept `developer`), and
  `compat.thinkingFormat: "zai"` sends GLM's thinking parameter format.
- `settings.json` sets `defaultProvider: glm` and `defaultModel: $GLM_MODEL`,
  because ACP `session/new` does not select a model; plus `quietStartup` and
  `enableInstallTelemetry: false`.

The disposable `HOME` keeps Pi's session files and pi-acp's
`~/.pi/pi-acp/session-map.json` writable by whichever unprivileged uid the runtime
chooses, and isolates Cases.

The launcher also sets:

- `PI_OFFLINE=1` (plus `PI_SKIP_VERSION_CHECK=1`): upstream otherwise calls
  `pi.dev/api/latest-version` and `pi.dev/api/report-install` at startup, and may
  try to refresh model catalogs, update packages or download `fd`/`rg` from GitHub.
  None of that is on the admitted route and the interceptor would reject the trace
  as undeclared egress. `ripgrep` and `fd-find` are installed in the image so Pi's
  search tools work without downloads.
- `npm_config_offline=true` and `npm_config_update_notifier=false`: pi-acp
  0.0.33 runs `npm view @earendil-works/pi-coding-agent version` on every ACP
  `session/new` to build an "update available" notice, with no switch to turn it
  off, and npm checks `registry.npmjs.org` for its own updates. Without these the
  first evaluation run was rejected with `egress_denied` for
  `GET registry.npmjs.org/@earendil-works%2fpi-coding-agent` and `GET .../npm`.
  With npm offline the lookup fails fast from the empty cache and the notice is
  omitted. The variables are inherited by Pi's shell tool, so `npm` there is also
  offline (the container has no other egress anyway).
- `PI_TELEMETRY=0`: disables install telemetry and provider attribution headers.
- `PI_ACP_PI_COMMAND`: points pi-acp at the locked `pi` binary instead of
  whatever `pi` is first on `PATH`.

Pi does not run a sandbox of its own, so no sandbox switch is needed under the
container's `--cap-drop=ALL` limits. pi-acp discards the child's stderr.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

# oh-my-pi ACP deployment

This unit installs the pinned [oh-my-pi](https://github.com/can1357/oh-my-pi)
release `18.2.11` (npm `@oh-my-pi/pi-coding-agent`, tag `v18.2.11`, commit
`e4151593`, MIT) and drives its **native** ACP server (`omp acp`) over stdio.
oh-my-pi is a large fork of the Pi coding agent (unit `24-pi-coding-agent`), but
unlike upstream Pi it needs no `pi-acp` bridge. ABB keeps each Case in a separate
empty workspace. No upstream source is vendored or modified.

`agent.toml` `[source]` and `source-manifest.json` pin the repository commit that
npm `18.2.11` was published from.

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

## Installation

`install/` holds only a `package.json` and `package-lock.json` that pin
`@oh-my-pi/pi-coding-agent@18.2.11` and `bun@1.4.2`. omp's CLI is a Bun program
(`engines.bun >= 1.3.14`), so the Bun runtime comes from the same lock (the
`@oven/bun-linux-*` optional package) instead of a curl installer. The image runs
`npm ci --ignore-scripts` (integrity-checked) and then only Bun's own
`install.js`, which copies the binary out of the locked platform package without
network access. Other install scripts are skipped: `onnxruntime-node` (an optional
dependency of an unused local-embedding feature) would download binaries.

At build time `bootstrap/list_providers.ts` reads the installed catalog and writes
`/opt/agent/builtin-providers.json`, the ids of every built-in provider
(bundled, models.dev-overlay and endpoint-discovery providers). It makes no
network calls.

## Launcher behavior

For every Case `bootstrap/launch.py` validates the three variables, creates a
disposable `HOME` under `/tmp` and writes omp's native config there
(`~/.omp/agent`, also passed as `PI_CODING_AGENT_DIR`, files mode 0600):

- `models.yml` declares a custom `glm` provider with `api: openai-completions`,
  the base URL, and one model `$GLM_MODEL` (`reasoning: true`, 200k context,
  32k max output, `compat.supportsDeveloperRole: false` because GLM rejects the
  `developer` role). `apiKey` is the environment variable *name* `GLM_API_KEY`,
  which omp resolves at request time, so the credential never touches disk or argv.
- `config.yml` sets `modelRoles.default: glm/$GLM_MODEL`, because ACP
  `session/new` does not select a model, and `disabledProviders` to every
  built-in provider id from `builtin-providers.json` plus the implicit local
  providers (`ollama`, `llama.cpp`, `lm-studio`).

Why `disabledProviders`: after each session is created omp starts a background
model-catalog refresh that probes keyless provider endpoints and the models.dev
mirror for every enabled built-in provider. The first local run was rejected by
host acceptance with `egress_denied` for `GET catalog.stencil.so/models.json.zstd`,
`coding-intl.dashscope.aliyuncs.com/v1/models`, `hyper.charm.land/v1/models`,
`api.venice.ai/api/v1/models`, `api.kilo.ai/api/gateway/models`,
`zenmux.ai/api/v1/models` and `api.commandcode.ai/provider/v1/models`. omp has no
offline switch for this refresh; disabling the unused providers through its own
setting leaves only the configured `glm` provider and needs no extra egress.

The launcher also sets `OTEL_SDK_DISABLED=true` (omp's own OTLP exporter stays
off; ABB's evidence comes from ACP events and model interception) and
`npm_config_offline=true` / `npm_config_update_notifier=false` for commands the
agent runs. The disposable `HOME` keeps omp's sessions, logs, model cache and
Bun's transpiler cache writable by whichever unprivileged uid the runtime
chooses, and isolates Cases.

omp does not run a sandbox of its own, so no sandbox switch is needed under the
container's `--cap-drop=ALL` limits.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

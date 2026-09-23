# Kode CLI ACP deployment

This unit installs the pinned [Kode CLI](https://github.com/shareAI-lab/Kode-CLI)
release `2.2.1` (npm `@shareai-lab/kode`, published from commit `b5fff92e`,
Apache-2.0) and drives its **native** ACP server (`kode --acp`, the same server
the package's `kode-acp` bin starts; see upstream `docs/acp.md`) over stdio.
ABB keeps each Case in a separate empty workspace. No upstream source is vendored
or modified.

`agent.toml` `[source]` and `source-manifest.json` pin the repository commit that
npm `2.2.1` was published from (its `gitHead`; upstream did not tag `v2.2.1`).

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
`@shareai-lab/kode@2.2.1`. The image runs `npm ci --ignore-scripts`
(integrity-checked). Two install scripts are skipped on purpose:

- Kode's own `postinstall` only tries to download a native binary from GitHub
  Releases; without it `kode-acp` falls back to the Node.js entry point
  `dist/index.js --acp`, which is what the launcher runs directly.
- `@vscode/ripgrep`'s `postinstall` downloads `rg`; Kode prefers `rg` on `PATH`,
  so the image installs Debian's `ripgrep` instead.

## Launcher behavior

For every Case `bootstrap/launch.py` validates the three variables, creates a
disposable `HOME` under `/tmp` and writes Kode's global config
`~/.kode/config.json` (directory 0700, file 0600, also passed as
`KODE_CONFIG_DIR`):

- one model profile with Kode's built-in `glm-coding` provider, `baseURL`
  `$GLM_API_BASE_URL`, model `$GLM_MODEL` (8k max output, 128k context). For
  `glm-5.x` model names Kode selects its Chat Completions adapter.
- `modelPointers` `main`/`task`/`compact`/`quick` all set to that profile,
  because ACP `session/new` does not select a model.
- `hasCompletedOnboarding: true` and `autoUpdaterStatus: disabled`.

Kode reads the API key only from the model profile; custom profiles have no
environment-variable reference at runtime (`kode models import` resolves
`apiKey.fromEnv` once and stores the value). The launcher therefore writes the
key into that 0600 file inside the per-Case temporary `HOME`. It is never baked
into the image, placed in argv or committed; under ABB interception the value
the container sees is the runtime's surrogate credential.

The launcher also sets `KODE_OFFLINE=1`, which makes Kode skip its npm registry
version check (`registry.npmjs.org` is not on the admitted route), and
`npm_config_offline=true` / `npm_config_update_notifier=false` for commands the
agent runs. The disposable `HOME` keeps Kode's ACP session files and logs
writable by whichever unprivileged uid the runtime chooses, and isolates Cases.

Kode's optional system sandbox needs `bwrap`, which is not installed; commands
run directly under the container's `--cap-drop=ALL` limits. Kode also ships
`WebSearch`/`WebFetch` tools; they have no admitted route here, so the profile
states that web access is unavailable.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

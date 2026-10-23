# Mastra Code ACP deployment

This unit installs the pinned [Mastra Code](https://github.com/mastra-ai/mastra/tree/main/mastracode)
CLI, npm package `mastracode@0.41.0` (tag `mastracode@0.41.0`, commit `429d7b9f`),
and runs its built-in ACP server (`mastracode --acp`,
`mastracode/tui/src/main.ts` -> `@mastra/code-sdk/acp`). ABB invokes it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

## Licence

`mastracode` and `@mastra/code-sdk` are Apache-2.0. The Mastra repository and the
published `@mastra/core` package also contain `ee/` directories (e.g.
`@mastra/core/dist/agent-builder/ee`, `auth/ee`) under the separate Mastra
Enterprise License; per the package `LICENSE.md` everything outside `ee/` is
Apache-2.0. The unit only installs the unmodified npm packages at runtime and
does not use the `ee/` agent-builder or auth features.

## Model provider

This unit uses default model selection; no `[model]` declaration is needed. Configure the selected provider in
`.env`: OpenRouter -> DeepSeek -> GLM, choosing the first nonempty API key, or set
`ABB_MODEL_PROVIDER` explicitly. Supply the selected provider's model name as well.
See [model selection](../../../docs/Model-Selection.md) for variables and constraints.

ABB passes the resolved configuration through internal `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_PROVIDER` variables.
Users do not fill these internal variables. Only the selected credential reaches the
launcher. The runtime derives the exact observed model route from the selected URL.

## Distribution

`install/package.json` pins `mastracode` `0.41.0`; `install/package-lock.json`
records the resolved tree with npm integrity hashes. The Dockerfile runs
`npm ci --omit=dev` on `node:24-bookworm` (package engine: Node >= 22.19) and
checks that the CLI loads.

## Launcher behavior

`bootstrap/launch.py` validates the three variables (HTTPS base URL without query
or fragment) and prepares, for every Case, a disposable `HOME` under `/tmp` with
XDG directories inside it and `MASTRA_APP_DATA_DIR=$HOME/mastracode`, where
Mastra Code keeps `settings.json`, its libsql thread database, vector store and
locks. It then runs `mastracode --acp` as a child with inherited stdin and
forwarded signals, relaying its stdout line by line (see "stdout relay" below).

`settings.json` (mode 0600, only in the disposable directory) contains:

- `customProviders: [{name: "abb-shared", url: $ABB_AGENT_MODEL_BASE_URL, apiKey: <runtime
  credential>, models: [$ABB_AGENT_MODEL]}]`. Mastra Code reads a custom provider's key
  only from this file (there is no env-var indirection for custom providers).
  Inside ABB the runtime value is the selected upstream credential, and the
  file is discarded with the container;
- `models.modeDefaults` for the three ACP modes (`build`, `plan`, `fast`) and the
  observational-memory observer/reflector and `/goal` judge models, all set to
  `abb-shared/$ABB_AGENT_MODEL`, so no role falls back to a built-in pack on another
  provider;
- a completed `onboarding` record so no first-run pack picker or login is needed.

Environment: `MASTRA_TELEMETRY_DISABLED=1` (PostHog analytics) and
`MASTRA_OFFLINE=1` (provider-registry background sync).

The ACP server runs without `--dangerous-auto-approve`, so tool approvals go
through ACP `session/request_permission` whenever Mastra Code asks for them;
ABB answers with its `allow_once` policy.

### stdout relay

When the process exits, Mastra Code's terminal library writes terminal reset
escape sequences (`ESC[?2004l`, `ESC[?25h`, ...) to stdout after the last
JSON-RPC message. ABB's ACP client logged `Error parsing JSON-RPC message` for
that line in the first local smoke. The launcher forwards every stdout line that
starts with `{` unchanged and moves any other line to stderr; no JSON-RPC message
is modified.

## Network routes

Besides the model route, `network/rules.toml` declares two optional public
metadata routes: `GET https://models.dev/api.json` and
`GET https://api.netlify.com/api/v1/ai-gateway/providers`. On ACP `session/new`
Mastra Code lists available models "best effort" through its default model
gateways, and those gateways fetch these unauthenticated provider catalogs
(`MASTRA_OFFLINE` does not cover this path). The results only populate the ACP
`models` list; the session model is taken from `settings.json`.

## Evidence

Mastra Code executes its tools itself (not through ACP `fs/*` or `terminal/*`
delegation). ACP evidence consists of `tool_call` / `tool_call_update`
notifications (tool name as title, ACP kind, raw input and output), streamed
`agent_message_chunk` text and the prompt result usage. File effects are captured
by ABB's workspace file evidence, and model traffic by the interceptor.

## Known behavior

- Upstream maps a Mastra Code run that ends in `error` to ACP stop reason
  `end_turn` (`mapStopReason` in `@mastra/code-sdk/acp/agent.ts`), so a model
  failure can surface as an ordinary turn end; check the model trace.
- The ACP `initialize` response reports `agentInfo.version = "0.1.0"`
  (hard-coded upstream), not the package version.
- `newSession` ignores the ACP `cwd` parameter; the project directory is the
  process working directory, which ABB sets to the Case workspace.

## Web tools

Mastra Code registers `web_search`/`web_extract` through `@mastra/tavily` only when `TAVILY_API_KEY` is set (`@mastra/code-sdk/dist/tools/web-search.js`). `TAVILY_API_KEY` is an optional secret (`optional_secret_env_keys`); when it is
supplied, `web_search` and `web_extract` are offered and call `api.tavily.com` (`POST /search, /extract`),
declared as a tool route in `network/rules.toml`, so requests and results are forwarded
and recorded as tool evidence. Without the key the tools are not offered, as before.
Other non-model traffic goes to ABB's egress observer, which forwards allowlisted hosts
(the package registries by default), refuses the rest with 403 and records every attempt
in `egress.jsonl`; a refusal does not reject the Case (#137).

## Browser

Mastra Code's browser tools (`browser_goto`, `browser_snapshot`, `browser_evaluate`, …)
are off by default and are only created by the TUI entry: upstream `acpMain`
(`@mastra/code-sdk` 1.8.0 `dist/acp/index.js`) never passes a browser to
`createMastraCode`. `bootstrap/abb-acp-browser.mjs` is that `acpMain` plus the browser
built from `settings.json` (`createBrowserFromSettings`), using only the SDK's exports;
`launch.py` runs it instead of `mastracode --acp` and enables the headless
`agent-browser` provider with `executablePath=/usr/local/bin/abb-chromium`.
Playwright talks to Chromium over a pipe, so no loopback route is needed. The image
installs Debian's Chromium; `abb-chromium` imports the interceptor CA into Chromium's
NSS store (Chromium ignores `SSL_CERT_FILE`) and `zz-abb-lean` keeps Chromium within the
128-pid budget (#158).

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

## Validation scope

Earlier acceptance records describe the previous fixed-provider deployment. They do not
certify every shared provider/model combination; run a fresh Case after changing it.

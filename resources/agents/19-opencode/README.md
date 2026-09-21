# OpenCode ACP deployment

## Requires: interceptor reply-traffic rule

`opencode acp` is a thin ACP front end: it starts OpenCode's HTTP server in the same
process on `127.0.0.1:4096` and drives it over REST/SSE through the bundled SDK
client (`packages/opencode/src/cli/cmd/acp.ts`); v1.18.31 has no in-process or
Unix-socket alternative. The interceptor netfilter redirects every non-root TCP
connection, loopback included, to the proxy, so:

- `network/rules.toml` declares a non-required loopback tool route
  (`127.0.0.1:4096`, only the endpoints the ACP front end calls). These calls appear
  as `tool_request`/`tool_response` in `network.jsonl`; nothing leaves the container.
- The proxy's forwarded connection to that server only works if the interceptor
  also accepts reply packets, i.e. `iptables -A OUTPUT -m conntrack --ctstate
  ESTABLISHED,RELATED -j ACCEPT` before the final `REJECT` in
  `agentbench/services/model-interceptor/.../proxy/netfilter.py`. Without it the
  server's replies are rejected and `session/new` hangs until the handshake timeout.
  This unit was certified with that rule applied as a local ABB patch; it must land
  in ABB before this unit works on an unpatched runtime.

This unit installs the pinned [OpenCode](https://github.com/anomalyco/opencode)
release `1.18.31` (tag `v1.18.31`, commit `014614d3`, MIT) from npm and runs its
built-in ACP server (`opencode acp`). ABB invokes it over ACP stdio and keeps each
Case in a separate empty workspace. No upstream source is vendored or modified.

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

## Distribution

`agent/` holds only a `package.json` and `package-lock.json` that pin
`opencode-ai@1.18.31` and `@opencode-ai/plugin@1.18.31`. The image runs
`npm ci --omit=dev --ignore-scripts`, so registry tarball integrity is checked,
then runs opencode-ai's own `postinstall.mjs` explicitly. That script only links
the prebuilt binary from the locked `opencode-linux-x64` (or `-baseline` on CPUs
without AVX2) package to `node_modules/.bin/opencode`; it downloads nothing when
the locked package is present. The script is run explicitly because npm 12 holds
install scripts for approval instead of running them. `ripgrep` comes from Debian so OpenCode does not
download its own copy at first search.

## Launcher behavior

`bootstrap/launch.py` validates the three variables and, for every Case, creates
a disposable `HOME` under `/tmp` with `XDG_CONFIG_HOME`, `XDG_DATA_HOME`,
`XDG_STATE_HOME` and `XDG_CACHE_HOME` inside it. This keeps OpenCode's config,
SQLite session store and cache writable by whichever unprivileged uid the runtime
chooses, and isolates Cases. It then writes `$XDG_CONFIG_HOME/opencode/opencode.json`
and execs `opencode acp`.

The config declares a `glm` provider on the bundled `@ai-sdk/openai-compatible`
SDK (compiled into the OpenCode binary, so no provider package is fetched) with
`baseURL` from `GLM_API_BASE_URL` and `apiKey` set to the literal reference
`{env:GLM_API_KEY}`, which OpenCode resolves itself. The key is passed only through
the environment, never argv or a file. `model` and `small_model` are
`glm/$GLM_MODEL`, so the model is selected at startup; `enabled_providers` is
limited to `glm`.

Each remaining setting removes a network call outside the admitted route, or a
background model call, because the interceptor rejects a trace with any
undeclared egress:

- `OPENCODE_DISABLE_MODELS_FETCH=1`: no models.dev catalog download
  (`models.opencode.ai` was contacted at startup on the host probe).
- Plugin dependency install: at startup OpenCode runs a background
  `npm install @opencode-ai/plugin` in each config directory unless that directory
  already has `node_modules` and a `package.json`/`package-lock.json` pair that
  declares and locks the package. There is no switch for this. The launcher copies
  the pinned `install/package*.json` into the config dir and symlinks `node_modules`
  to the image's installed tree, so the check passes and `registry.npmjs.org` is
  never contacted.
- `OPENCODE_DISABLE_AUTOUPDATE=1`, `autoupdate: false`: no release check.
- `OPENCODE_DISABLE_SHARE=1`, `share: "disabled"`: no share service.
- `OPENCODE_DISABLE_DEFAULT_PLUGINS=1`, `OPENCODE_PURE=1`: no built-in auth plugins
  for other providers and no external plugin loading.
- `OPENCODE_DISABLE_LSP_DOWNLOAD=1`: language servers are not downloaded on demand.
- `OPENCODE_DISABLE_CLAUDE_CODE=1`, `OPENCODE_DISABLE_EXTERNAL_SKILLS=1`: no
  prompts or skills are imported from outside the disposable HOME.
- `permission.webfetch: "deny"`: the web fetch tool would reach arbitrary hosts, so
  it is hidden from the model. Web search is already off for non-OpenCode providers.
- `agent.title.disable: true`: OpenCode otherwise starts a separate background
  model call on the small model to title the session after the first turn; the
  one-shot worker closes ACP before it finishes, which cut the request.

`opencode acp` starts its own HTTP server inside the container and talks to it
locally; the launcher pins it to `--hostname 127.0.0.1 --port 4096` (the default
would fall back to a random port if 4096 were taken). This is loopback traffic,
not egress, but see "Requires" above.

## Known non-blocking noise

When the one-shot worker closes ACP, the long-lived `GET /global/event` SSE stream
through the interceptor is cut and recorded as one `tool_error`
(`transport_error`, incomplete chunked read). The route is `required = false` and
the host accepts the trace.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

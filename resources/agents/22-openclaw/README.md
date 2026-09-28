# OpenClaw ACP deployment

This unit installs the pinned [OpenClaw](https://github.com/openclaw/openclaw)
release `2026.9.5` (tag `v2026.9.5`, commit `ec9c1a13`) from npm and drives it
through its built-in ACP bridge (`openclaw acp`). ABB invokes the bridge over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is
vendored or modified.

License: MIT (the repository's `LICENSE` file and the npm package's `license`
field). GitHub's license detection reports `NOASSERTION` for the repository.

The acceptance profile uses Zhipu GLM's OpenAI-compatible coding endpoint.
Supply these variables only at runtime:

- `GLM_API_BASE_URL`: the OpenAI-style base URL, e.g.
  `https://open.bigmodel.cn/api/coding/paas/v4`.
- `GLM_MODEL`: the exact provider model ID, such as `glm-5.1`.
- `GLM_API_KEY`: the Bearer credential. It is never written into this unit.

The interception manifest admits only the tested model route:
`POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`.
A different OpenAI-compatible provider needs an explicit reviewed route update;
changing environment variables alone does not broaden container egress.

`network/rules.toml` adds two non-model routes, both `required = false`:

- `GET 127.0.0.1:18799 /` (purpose `tool`): the bridge's WebSocket upgrade to
  the in-container Gateway. The runtime redirects every non-root TCP connection,
  loopback included, through the interceptor, so the bridge-to-Gateway hop is
  otherwise rejected as undeclared egress. It never leaves the container. Relaying
  the Gateway's replies also relies on the interceptor admitting
  `ESTABLISHED,RELATED` output, as for the other loopback-server units.
- `GET clawhub.ai:443 /v1/feeds/plugins` (purpose `metadata`): the Gateway's
  post-ready dashboard prewarm (`listManagedPlugins`) fetches the public ClawHub
  plugin catalog feed. v2026.9.5 exposes no config or env switch for it; OpenClaw
  falls back to its bundled catalog when the call fails.

## Why there are two processes

`openclaw acp` is only a bridge: it speaks ACP on stdio and forwards prompts over
WebSocket to an OpenClaw Gateway, and the Gateway runs the agent loop and makes
the model calls. So `bootstrap/launch.py` runs a private Gateway inside the
container for each Case:

1. validates the three `GLM_*` variables (HTTPS base URL, no query/fragment);
2. creates a disposable `HOME` under `/tmp` and writes `~/.openclaw/openclaw.json`
   there, keeping OpenClaw's config, state and sessions writable by whichever
   unprivileged uid the runtime chooses and isolated per Case;
3. generates a random Gateway token per Case and pins the Gateway to
   `127.0.0.1:18799` (the admitted loopback route);
4. starts `openclaw gateway run` as a child with its console output redirected to
   `$HOME/gateway.log` (ACP stdout must stay pure JSON-RPC), and waits up to 150 s
   for its `[gateway] ready` line;
5. starts `openclaw acp --url ws://127.0.0.1:<port> --token-file <0600 file>`
   with inherited stdio, forwards SIGTERM/SIGINT to it, and stops the Gateway
   when the bridge exits (ABB also kills the whole process group).

The GLM key reaches only the Gateway, through its environment; the config
references it as `${GLM_API_KEY}` and OpenClaw expands it at load time, so the
key is never written to disk or placed in argv. The bridge gets neither the key
nor the token variable (it reads the token file).

## Config choices

- `models.providers.glm` (`api: openai-completions`) with
  `agents.defaults.model.primary = glm/$GLM_MODEL`, so the model is chosen at
  startup (ACP `session/new` cannot select one).
- `update.checkOnStart=false`, `update.auto.enabled=false`, `telemetry.enabled=false`,
  `models.catalogRefresh.enabled=false` and `OPENCLAW_DISABLE_BONJOUR=1`: update
  checks, telemetry and the remote model catalog (`catalog.openclaw.ai`, fetched at
  Gateway startup otherwise) would be egress outside the admitted routes; mDNS is
  pointless in a one-shot container.
- `agents.defaults.cwd` = the ACP working directory (`/home/agent/workspace`), so
  file and exec tools operate on the Case workspace while OpenClaw's managed
  workspace (memory, persona files) stays in the disposable `HOME`.
- `agents.defaults.skipBootstrap=true`: a fresh workspace otherwise gets
  `BOOTSTRAP.md`, a first-run "birth sequence" persona ritual unrelated to the Case.
- `agents.defaults.heartbeat.every="0m"`: disables recurring heartbeat turns,
  which are model calls without a Case prompt.
- `OPENCLAW_HIDE_BANNER=1`, `OPENCLAW_SUPPRESS_NOTES=1`, `NO_COLOR=1` keep the
  bridge's stdout clean.

## Image

`agent/` holds only a `package.json` and `package-lock.json` that pin
`openclaw@2026.9.5`; the image installs it with `npm ci --omit=dev --ignore-scripts`,
so registry tarball integrity is checked and no upstream file is edited.
Dependency install scripts (native prebuild helpers of `koffi`, `tree-sitter-bash`,
`protobufjs`, a no-op in `@google/genai`) are skipped; the host probe ran the same
way. OpenClaw's own `preinstall`/`postinstall` only prune and finalize its package
directory, and its launcher refuses to start (`package lifecycle is incomplete`)
until they have run, replaying them itself on first launch. The runtime uid
cannot write `/opt/agent`, so the Dockerfile triggers that replay once at build
time with `openclaw --version` and fails the build if the pending marker remains.
The package requires Node `>=24.16 <25 || >=26.1`;
`node:24-bookworm` currently ships Node 24.21.

## Known non-blocking noise

- The bridge logs `[config] warnings: ... env var "OPENCLAW_GATEWAY_TOKEN" /
  "GLM_API_KEY" - feature using this value will be unavailable` on stderr. It loads
  the shared config but deliberately does not receive those variables.
- The Gateway may warn about pending plugin state migrations and about missing
  vector embeddings for memory search; neither makes network calls.
- The last model call of a Case can be recorded as a native `Client disconnected`
  transport error when the one-shot worker closes ACP and the launcher stops the
  Gateway right after the final answer has been delivered. The step output is
  complete and host acceptance is unaffected.
- The agent's self-description comes from OpenClaw's generic system prompt and can
  mention channels or web research that this unit does not provision.
- OpenClaw's system prompt is large (about 52k tokens), so the first model call
  of a Case is slow; `timeout_sec = 900` and `handshake_timeout = 180` allow for it.

## Installation inputs

Tracked installation manifests live in install/. Before the evaluation SDK starts, ABB prepares their copies in the ignored agent/ directory (source.method = install). Docker builds use those generated copies. Do not edit agent/; edit install/ instead. If an existing copy differs, move agent/ aside and rerun to regenerate it.

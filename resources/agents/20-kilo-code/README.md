# Kilo Code CLI ACP deployment

This unit installs the pinned [Kilo Code CLI](https://github.com/Kilo-Org/kilocode)
release `7.7.5` (tag `v7.7.5`, commit `01ef456f`, MIT license) from npm and runs its
built-in ACP server (`kilo acp`). ABB invokes it over ACP stdio and keeps each Case
in a separate empty workspace. No upstream source is vendored or modified.

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

## Install

`agent/` holds only a `package.json` and `package-lock.json` that pin
`@kilocode/cli@7.7.5`; the image installs it with `npm ci`, so registry tarball
integrity is checked. The npm package is a small Node launcher plus a
platform-specific prebuilt binary (`@kilocode/cli-linux-x64` and variants,
selected by npm's `os`/`cpu`/`libc` filters and the package's own postinstall).

## Launcher behavior

For every Case `bootstrap/launch.py` validates the three variables, creates a
disposable `HOME` under `/tmp`, points `XDG_CONFIG_HOME`/`XDG_DATA_HOME`/
`XDG_STATE_HOME`/`XDG_CACHE_HOME` inside it, writes `~/.config/kilo/kilo.json`,
and `exec`s `kilo acp`. The disposable HOME keeps Kilo's config, SQLite session
database and logs writable by whichever unprivileged uid the runtime chooses, and
isolates Cases.

The generated config:

- declares one provider, `glm`, using the `@ai-sdk/openai-compatible` adapter that
  is bundled in the Kilo binary (no runtime npm install), with `baseURL` from
  `GLM_API_BASE_URL` and `apiKey: "{env:GLM_API_KEY}"`, so the key reaches Kilo
  only through the environment and never through argv or a file;
- sets `model` and `small_model` to `glm/$GLM_MODEL`, because ACP `session/new`
  does not choose a model;
- sets `enabled_providers: ["glm"]`, so the built-in Kilo gateway
  (`api.kilo.ai`) and other catalog providers are not loaded;
- disables auto-update and sharing;
- disables the built-in `title` agent. Otherwise Kilo starts a second,
  background model call after the first turn to name the session; the one-shot
  worker closes ACP before it finishes and the interceptor records a cut request.

The launcher also sets these upstream environment switches, each of which stops a
startup call outside the admitted model route (the interceptor would otherwise
reject the trace as undeclared egress):

| Variable | Stops |
|---|---|
| `KILO_DISABLE_MODELS_FETCH=1` | models.dev catalog download |
| `KILO_TELEMETRY_LEVEL=off` | PostHog telemetry (`us.i.posthog.com`) |
| `KILO_DISABLE_AUTOUPDATE=1` | release check |
| `KILO_DISABLE_SESSION_INGEST=1`, `KILO_DISABLE_PRESENCE=1`, `KILO_DISABLE_SHARE=1` | Kilo cloud session sync, presence, sharing |
| `KILO_DISABLE_DEFAULT_PLUGINS=1` | runtime plugin downloads from npm |
| `KILO_DISABLE_LSP_DOWNLOAD=1` | language-server downloads |
| `KILO_DISABLE_CODEBASE_INDEXING=1` | embedding-based indexing |
| `KILO_DISABLE_CLAUDE_CODE=1`, `KILO_DISABLE_EXTERNAL_SKILLS=1` | importing settings/skills from other tools |

These switches are read by the 7.7.5 binary but are not all documented upstream;
re-check them when bumping the pin.

Tool permission prompts are forwarded over ACP and answered by ABB's
`allow_once` policy.

## Loopback server route

`kilo acp` is a thin ACP bridge over Kilo's own HTTP server: the same process
starts the server on loopback and the bridge drives config, agents, sessions,
prompts, permissions and the `/global/event` SSE stream through its REST API.
Upstream offers no Unix-socket or in-process transport for `kilo acp`.

The runtime redirects every non-root TCP connection, loopback included, to the
interceptor, so these calls are policy-checked like any other request. The
launcher pins the server to `127.0.0.1:4096` (`--hostname`/`--port`), and
`network/rules.toml` admits only that address and port, with the server's API
path groups, as a non-required tool route (`purpose = "tool"`,
`required = false`). The traffic never leaves the container; it appears in
`network.jsonl` as `tool_request`/`tool_response` pairs on `127.0.0.1`. Model
calls remain restricted to the single GLM route above.

## Requires

The unit depends on the interceptor's netfilter rules accepting reply traffic of
admitted loopback connections, i.e.
`iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT`
before the final `REJECT` in
`agentbench/services/model-interceptor/src/defuzex_model_interceptor/proxy/netfilter.py`.
The interceptor connects to `127.0.0.1:4096` as root, but the Kilo server's
replies are owned by the agent uid; without that rule they hit the `REJECT`,
every bridge call hangs, and the Case times out (`tool_error ... client
disconnected` on `/config`, `/agent`, `/global/event`).

## Known non-blocking noise

- The bridge's long-lived `GET /global/event` SSE stream is still open when the
  one-shot worker closes ACP, so each Case records one `tool_error`
  (`transport_error`, `client disconnected`) on that path. The route is not
  required and the host accepts the trace.

Kilo ships a bubblewrap-based command sandbox. It is off by default and this unit
leaves it off: bubblewrap needs user namespaces, which the container
(`--cap-drop=ALL`, `no-new-privileges`) does not grant.

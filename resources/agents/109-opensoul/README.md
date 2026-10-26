# OpenSoul

Onboards [NJX-njx/opensoul](https://github.com/NJX-njx/opensoul) at commit
`5478591f9f031e6537193cbc828150193c0f478c`. OpenSoul is a self-hosted AI agent
runtime for cross-surface task continuity; it ships a native ACP bridge
(`opensoul acp`) that forwards prompts to a locally running OpenSoul Gateway
over WebSocket.

## Why ACP

OpenSoul exposes an ACP server (`opensoul acp`) that speaks the Agent Client
Protocol over stdio and translates each ACP session into a Gateway session.
`agentbench` talks to it exactly as it does to any other ACP agent: one
`initialize`, one `new_session`, then `prompt`/tool round-trips. The Gateway is
the agent runtime and owns the model; the bridge is a protocol adapter.

## Two-process runtime

The container runs two processes, both started by `bootstrap/launch.py`:

1. **Gateway** - `node opensoul.mjs gateway --allow-unconfigured --bind loopback`
   (background, logs to `<home>/gateway.log`). It binds `127.0.0.1:18789` and,
   with `OPENSOUL_SKIP_CHANNELS=1`, does not start any messaging channels.
2. **ACP bridge** - `node opensoul.mjs acp --url ws://127.0.0.1:18789 --session agent:main:main`
   (foreground, exec'd). This is the stdio ACP server `agentbench` drives.

The Gateway must be listening before the bridge starts; the launcher polls the
port and only then execs the bridge.

## Model mapping

`bootstrap/launch.py` reads the shared runtime variables and writes
`~/.opensoul/opensoul.json` before starting either process:

| ABB runtime variable          | OpenSoul config                                  |
| ----------------------------- | ------------------------------------------------ |
| `ABB_AGENT_MODEL_API_KEY`     | `models.providers.deepseek.apiKey` (as `${DEEPSEEK_API_KEY}`) |
| `ABB_AGENT_MODEL_BASE_URL`    | `models.providers.deepseek.baseUrl`              |
| `ABB_AGENT_MODEL`             | provider model id + `agents.defaults.model.primary` |

DeepSeek is not one of OpenSoul's built-in providers, so it is declared as a
custom `openai-completions` provider. The API key is never written to disk: the
config stores `${DEEPSEEK_API_KEY}` (OpenSoul substitutes `${VAR}` references
from the environment at load time), and the value itself is only exported to the
child environment.

## Build

`pnpm install --frozen-lockfile` then `OPENSOUL_A2UI_SKIP_MISSING=1 pnpm build`
(OpenSoul's own build recipe). The A2UI canvas bundle is skipped because its
prebuilt `a2ui.bundle.js` is not committed and the `vendor/`/`apps/` sources are
excluded from the Docker context; the Gateway and ACP bridge do not need it.
The full workspace (`packages/*` and `extensions/*`) must be present for the
frozen install because those packages are `link:` importers in the lockfile.

After the build, `install/patch-acp-final.mjs` patches the compiled ACP bridge:
the upstream translator only forwards text from throttled `delta` chat events and
drops the terminal `final` event's full text, so streamed replies are cut off.
The patch makes the `final` branch flush the remaining text before ending the
turn. It is applied to the built bundle only; the pinned `agent/` source is
untouched.

## Source provenance

- Repository: <https://github.com/NJX-njx/opensoul>
- Revision: `5478591f9f031e6537193cbc828150193c0f478c`
- Acquisition: `[source] method = "git"` (pinned commit, restored by the runtime)

## Files

| Path                    | Purpose                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `agent.toml`            | Agent manifest (ACP adapter, shared model, git source)     |
| `Dockerfile`            | Builds OpenSoul + Python runtime, runs as uid 10001        |
| `bootstrap/launch.py`   | Starts Gateway, writes DeepSeek config, execs ACP bridge   |
| `network/rules.toml`    | Documents the admitted model route + egress observer       |
| `requirement.md`        | KUMA Agent Profile                                         |
| `source-manifest.json`  | Pinned source provenance                                   |
| `install/patch-acp-final.mjs` | Flushes final-event text in the compiled ACP bridge   |

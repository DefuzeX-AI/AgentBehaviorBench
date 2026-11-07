# OpenCrabs ACP deployment

This unit installs the pinned [OpenCrabs](https://github.com/opencrabs/opencrabs) release
`0.5.13` (tag `v0.5.13`, commit `0dfe3b7f`, MIT) as the upstream prebuilt Linux binary and
runs its built-in ACP server (`opencrabs acp`). ABB invokes it over ACP stdio and keeps each
Case in a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `opencrabs-v0.5.13-linux-amd64.tar.gz` from the `v0.5.13`
GitHub release by sha256 (`4dbce52e…1191cc21e`, the asset digest GitHub reports). The archive
contains `opencrabs` and its bundled `rtk` helper; the Dockerfile checks it with
`sha256sum -c` and installs both to `/opt/opencrabs/bin`.

The release binary is dynamically linked against glibc 2.43 and needs `libgomp`, so the
image is based on `ubuntu:26.04` (glibc 2.43) instead of the Debian Python images, with a
venv at `/opt/venv` for ABB's Python runtime.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case, writes `~/.opencrabs/config.toml` and
`~/.opencrabs/keys.toml` and runs `opencrabs acp --model <model>` as a child:

```toml
[providers.opencrabs]
enabled = false

[providers.custom.abb]
enabled = true
base_url = "http://127.0.0.1:<relay port>/v1/chat/completions"
default_model = "<model>"
models = ["<model>"]

[agent]
default_provider = "abb"
default_model = "<model>"
auto_update = false
```

The built-in OpenCrabs provider (its hosted inference proxy) is disabled, so the custom
`abb` provider is the only enabled one. `auto_update = false` turns off the startup
self-update from GitHub, which egress would refuse anyway. The launcher also creates
`~/.opencrabs/.fallback-chain-suggested`: on a fresh install OpenCrabs prepends a one-shot
"set up a fallback chain" system note to the first user message and then writes this marker
(`src/brain/agent/service/fallback_suggest.rs`). Every Case is a fresh `HOME`, so without
the marker every Case would carry that note and the agent would read its config and offer
a fallback setup in each answer. Everything else, including the tool approval policy and
lazy tool loading, keeps upstream defaults.

**Model relay (`bootstrap/model_relay.py`).** OpenCrabs reads a custom provider's key only
from `keys.toml`, so `keys.toml` holds a placeholder and the provider's `base_url` is a
plain-HTTP relay on an ephemeral `127.0.0.1` port (added to `NO_PROXY`). The relay sends
each `POST /v1/chat/completions` as `POST <selected-base>/chat/completions` through the
runtime's `HTTPS_PROXY` with Python's default TLS context, sets `Authorization` to the
selected key and streams the response back unchanged; anything else gets a local 404. The
real key is never written to disk or passed to OpenCrabs, which matters here because the
agent's `config_manager` tool can read its config files back into the conversation.
`ABB_AGENT_MODEL_API_KEY` is removed from OpenCrabs' environment. Every model call is still
intercepted and recorded.

**Permissions.** In the ACP session tool calls arrive as `session/request_permission`
requests, which ABB answers with its `allow_once` policy. The launcher sets `umask 0` so
directories the agent creates can be removed by the host after the Case.

No egress denials were observed in the smoke run: with the hosted provider and
self-update off, OpenCrabs' only network traffic is the model connection.

# Stakpak ACP deployment

This unit installs the pinned [Stakpak](https://github.com/stakpak/agent) release `0.3.88`
(tag `v0.3.88`, commit `d3eba6f5`, Apache-2.0) as the upstream prebuilt, statically linked
Linux binary and runs its built-in ACP server (`stakpak acp`). ABB invokes it over ACP
stdio and keeps each Case in a separate empty workspace. No upstream source is vendored
or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `stakpak-linux-x86_64.tar.gz` from the `v0.3.88` GitHub
release by sha256 (`1e923d6b…a7728490c6`; the release has no checksum file, the value
matches the asset digest GitHub reports). The Dockerfile downloads it, checks it with
`sha256sum -c`, installs the `stakpak` binary to `/opt/stakpak/bin/stakpak` and runs
`--version`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case, writes `~/.stakpak/config.toml` and runs
`stakpak acp` as a child:

```toml
[profiles.default]
provider = "local"
model = "openai/<model>"

[profiles.default.providers.openai]
type = "openai"
api_endpoint = "http://127.0.0.1:<relay port>/v1"

[settings]
collect_telemetry = false
```

Without a Stakpak API key Stakpak runs in local mode (`Running in local mode`): its tools
run locally and model calls go to the configured provider.

**Why the built-in OpenAI provider.** Over ACP Stakpak resolves only models prefixed
`anthropic/`, `openai/` or `google/` (`cli/src/commands/acp/server.rs`); anything else is
sent to the hosted Stakpak provider, which does not exist in local mode ("Provider not
found: stakpak"). So the unit uses the `openai` provider with a custom `api_endpoint`.
With a non-OpenAI endpoint that provider uses Chat Completions, but it sends the model as
`openai/<model>` and reads its key only from `OPENAI_API_KEY`.

**Model relay (`bootstrap/model_relay.py`).** The endpoint is a plain-HTTP relay on an
ephemeral `127.0.0.1` port (added to `NO_PROXY`) and `OPENAI_API_KEY` is a placeholder, so
the real key is never in Stakpak's config or environment; `ABB_AGENT_MODEL_API_KEY` is
removed from Stakpak's environment. The relay sends each `POST /v1/chat/completions` as
`POST <selected-base>/chat/completions` through the runtime's `HTTPS_PROXY` with Python's
default TLS context, removes the `openai/` prefix from the request's `model` field, sets
`Authorization` to the selected key and streams the response back unchanged; anything
else gets a local 404. Every model call is still intercepted and recorded.

**Permissions.** Stakpak's ACP server asks before file writes and commands
(`session/request_permission`); ABB answers with its `allow_once` policy. Its
`ask_user` tool returns `INTERACTIVE_REQUIRED` in this mode and the agent asks in its
reply instead. The launcher sets `umask 0` so directories the agent creates can be
removed by the host after the Case.

Known noise:
- Before starting the ACP session Stakpak checks GitHub for a newer release
  (`force_auto_update`). Egress refuses it, Stakpak prints `Update check failed` and
  continues with the pinned binary.
- Stakpak's MCP proxy also registers its hosted `paks` and `aap` servers at
  `https://apiv2.stakpak.dev`; egress refuses those connections (about five denials per
  Case) and the local tools are unaffected.

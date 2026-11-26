# agentty ACP deployment

This unit installs the pinned [agentty](https://github.com/agentty-org/agentty) release
`0.9.32` (tag `v0.9.32`, commit `b8c8b719`, MIT) as the upstream prebuilt, statically linked
Linux binary and runs its built-in ACP server (`agentty acp`). ABB invokes it over ACP stdio
and keeps each Case in a separate empty workspace. No upstream source is vendored or
modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

**Depends on #555**: agentty runs commands through ABB's ACP terminal.

## Distribution

`install/distribution.json` pins `agentty-linux-x86_64` from the `v0.9.32` GitHub release by
sha256 (`702dfd5c…ce944ad9eac699e6cda0abd8193c510d`, the release's `SHA256SUMS` entry). The
Dockerfile downloads it to `/opt/agentty/bin/agentty`, checks it with `sha256sum -c` and runs
`--version`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs agentty as a child:

```
agentty acp --provider 127.0.0.1:<relay port> -m <model> --sandbox off
```

with the key in `OPENAI_API_KEY` (agentty does not persist it).

**Model relay (`bootstrap/model_relay.py`, same as `70-pi-go`).** With an OpenAI-compatible
`--provider host[:port]` agentty sends `POST /v1/chat/completions` and lists
`GET /v1/models` at startup (checked against a local stub). The runtime admits exactly
`POST <selected-base>/chat/completions`, so the provider is a plain-HTTP relay on an
ephemeral `127.0.0.1` port (added to `NO_PROXY`). The relay sends each
`POST /v1/chat/completions` as `POST <selected-base>/chat/completions` through the runtime's
`HTTPS_PROXY` with Python's default TLS context and streams the response back unchanged;
anything else gets a local 404. Every model call is still intercepted and recorded.

**`--sandbox off`.** agentty wraps commands in its in-process claybin sandbox (seccomp +
landlock + cgroup2). In the runtime container every command failed with
`claybin: spawn failed: child setup (errno 38)` and nothing ran, although the help text says
a host that cannot run claybin falls back automatically. The unit uses agentty's documented
`--sandbox off`; the Case container is the isolation boundary. File tools stay confined to
the workspace (`--workspace`, default cwd), and agentty's default ACP permission profile
(`ask`: writes, commands and network are requested) is kept and answered by ABB's
`allow_once` policy. agentty runs commands through ABB's ACP terminal (as `/bin/sh -c`),
which is why #555 is needed for a clean workspace teardown. The launcher also sets `umask 0`.

Known noise: at startup agentty opens one connection to each hosted provider's API host
(OpenAI, Groq, OpenRouter, DeepSeek, …), which the egress policy refuses (about ten denials
per Case); the turn is unaffected.

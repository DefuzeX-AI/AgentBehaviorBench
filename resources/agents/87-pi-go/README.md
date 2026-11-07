# pi-go ACP deployment

This unit installs the pinned [pi-go](https://github.com/dimetron/pi-go) release `0.3.4`
(tag `v0.3.4`, commit `1c5d9738`, MIT) as the upstream prebuilt Linux binary (`pi`) and runs
its built-in ACP server (`pi acp-server`). ABB invokes it over ACP stdio and keeps each Case
in a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `pi-go_0.3.4_linux_amd64.tar.gz` from the `v0.3.4` GitHub
release by sha256 (`e135cbae…35a97ead`, the release's `checksums.txt` entry). The
Dockerfile downloads it, checks it with `sha256sum -c` and installs the single `pi` binary
to `/opt/pi-go/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs:

```
pi acp-server --model <model> --url <url>
```

with the key in `OPENAI_API_KEY`. With `--url`, pi-go treats a model name without a known
provider prefix (such as `deepseek-v4-flash`) as a custom OpenAI-compatible model, as its
README documents. The key is never on the command line or on disk.

**Model relay.** pi-go appends `/v1` to a `--url` that does not already end in `/v1` and
sends `POST <url>/v1/chat/completions` (checked against a local stub: `http://h`,
`http://h/v1` and `http://h/x` give `/v1/chat/completions`, `/v1/chat/completions` and
`/x/v1/chat/completions`). With a base URL such as `https://api.deepseek.com` that request
is not the admitted model route; the first smoke failed with every call refused by the
egress policy. For a base URL ending in `/v1` the launcher passes it straight through.
Otherwise `bootstrap/model_relay.py` serves plain HTTP on an ephemeral `127.0.0.1` port
(added to `NO_PROXY`), `--url` points at it, and the relay sends each
`POST /v1/chat/completions` as `POST <selected-base>/chat/completions` through the
runtime's `HTTPS_PROXY` with Python's default TLS context (which honors `SSL_CERT_FILE`),
streaming the response, including SSE and error statuses, back unchanged. Every model call
is still intercepted and recorded by the runtime; any other path gets a local 404. pi-go
runs as a child of the launcher so the relay stays alive, and inherits the ACP stdio
directly.

pi-go runs its tools (file writes and shell commands included) itself inside the
container; the smoke made no ACP `fs/*`, `terminal/*` or permission requests. The launcher
sets `umask 0` so directories the agent creates in ABB's host-owned workspace can be
removed after the run.

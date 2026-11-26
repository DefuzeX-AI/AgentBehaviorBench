# Aster ACP deployment

This unit installs the pinned [Aster](https://github.com/Zfinix/aster) release `0.7.1`
(tag `cli-v0.7.1`, commit `aa437a6f`, Apache-2.0) as the upstream prebuilt static Linux
binary and runs its built-in ACP server (`aster acp`). ABB invokes it over ACP stdio and
keeps each Case in a separate empty workspace. No upstream source is vendored or modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes
the resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL`
and `ABB_AGENT_MODEL`; the runtime admits the exact `POST <selected-base>/chat/completions`
route.

## Distribution

`install/distribution.json` pins `aster-0.7.1-x86_64-unknown-linux-musl.tar.gz` from the
`cli-v0.7.1` GitHub release by sha256 (`35d4278c…dcca7064`, the value in the release's
`.sha256` file). The Dockerfile downloads it, checks it with `sha256sum -c` and installs
the single `aster` binary to `/opt/aster/bin`.

## Launcher behavior

`bootstrap/launch.py` validates the model variables (HTTPS base URL without query or
fragment), creates a disposable `HOME` per Case and runs:

```
aster acp --no-mcp
```

with `ASTER_BASE_URL`, `ASTER_MODEL` and `ASTER_API_KEY` set; these outrank
`~/.aster/aster.yaml`, and Aster sends `POST <ASTER_BASE_URL>/chat/completions`. The key
stays in the environment, never on the command line or on disk.

**Model relay.** Aster's HTTP client is reqwest with `rustls-tls`, which trusts only its
bundled webpki roots and ignores `SSL_CERT_FILE`. It therefore cannot verify the
runtime's model interceptor (the first smoke failed with "Couldn't reach
api.deepseek.com" and no intercepted request). `bootstrap/model_relay.py` serves plain
HTTP on an ephemeral `127.0.0.1` port and `ASTER_BASE_URL` points at it (with
`127.0.0.1` added to `NO_PROXY`). The relay sends the same method, path, body and
`Authorization`/`Content-Type`/`Accept` headers to the selected HTTPS base URL with
Python's default TLS context (which honors `SSL_CERT_FILE`) through the runtime's
`HTTPS_PROXY`, and streams the response (including SSE and error statuses) back
unchanged. Every model request is still intercepted and recorded by the runtime. Only
`POST /chat/completions` is relayed, the one route the runtime admits; anything else
gets a local 404. In particular Aster's ACP session asks `GET /models` for its model
picker, which would otherwise be refused by the egress policy and retried (8 denied
attempts in the first relayed smoke).

Aster runs as a child of the launcher so the relay stays alive, and inherits the ACP
stdio directly.

Aster's default permission mode (`edit`: edits and commands run, only a policy rule stops
one) is kept. Aster executes its tools inside the container rather than through ACP
`fs/*` or `terminal/*`; there is no `bwrap`, so it uses its process-level sandbox
fallback. The launcher sets `umask 0` so directories the agent creates in ABB's
host-owned workspace can be removed after the run.

After the turn ends Aster may start one more model request without tools (a session
summary). When ABB closes the session this request is cut off and is recorded as
`llm_error: Client disconnected.`; it does not affect the turn's result.

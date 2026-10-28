# OpenClaudia (ABB unit)

Corvidae-Coding-Projects/OpenClaudia pinned at
`fad337c447320ea0a3281bcbff378b30e7a1d3d0`.

## Why LangGraph binding + print mode

Upstream `openclaudia acp` implements acpx **Agent Control Protocol**, not the
**Agent Client Protocol** used by ABB's ACP adapter (see issue #524 release
notes). This unit keeps upstream behaviour by calling the native one-shot
frontend:

```text
openclaudia --target local --model <model> --print "<prompt>"
```

Print mode is no-tools / no-persistence chat. Strategy group:
`basic-safety-general`.

OpenClaudia's reqwest `rustls-tls` client ignores `SSL_CERT_FILE`, so the binding
starts a loopback HTTP relay (`bindings/model_relay.py`) and points `local` at
it; the relay forwards to `https://api.openai.com` through the runtime
`HTTPS_PROXY` (same pattern as 113-sudocode / 81-aster).

## Layout

- `agent/` — ignored git checkout of the pinned revision (build context)
- `bindings/bridge.py` — synchronous `create_graph` factory
- `Dockerfile` — release build of `openclaudia`, then ABB worker image

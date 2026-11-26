# NullClaw ACP deployment

This unit builds [NullClaw](https://github.com/nullclaw/nullclaw) (`nullclaw/nullclaw`, revision
`5f1cade0`, version 2026.5.29) from source and runs its native ACP server (`nullclaw acp`,
newline-delimited JSON-RPC on stdio; each prompt runs `nullclaw agent invoke` with the session cwd
as workspace). ABB drives one ACP session per Case. `source.method = "git"` restores the pinned
checkout into `agent/`; no upstream file is modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route.

## Image

- Builder: `alpine:3.24` with the repository's own `.github/scripts/install-zig.sh` (Zig 0.16.0),
  then `zig build -Dtarget=x86_64-linux-musl -Doptimize=ReleaseSmall` for a static binary.
- Runtime: `debian:bookworm-slim` with `python3` for the ABB worker and `curl`/`git` for the
  agent. The PEP 668 marker is removed because ABB's SDK overlay runs
  `python -m pip --isolated install`.
- The system CA bundle `/etc/ssl/certs/ca-certificates.crt` is owned by the runtime user: Zig's
  std HTTP client reads only the system bundle, not `SSL_CERT_FILE`, so the launcher appends ABB's
  interception CA to it at start.

## Launcher (`install/abb-acp-launch.py`)

NullClaw reads model configuration only from `~/.nullclaw/config.json` (`docs/en/configuration.md`).
The launcher validates the three model variables, points `HOME` / `NULLCLAW_HOME` at a disposable
directory per Case and writes `config.json` (mode 0600) in the documented "Recommended Security
Config" shape:

```json
{
  "models": {"providers": {"<p>": {"api_key": "<key>", "base_url": "<selected base>"}}},
  "agents": {"defaults": {"model": {"primary": "<p>/<model>"}}},
  "memory": {"backend": "sqlite", "auto_save": true},
  "autonomy": {"level": "supervised", "workspace_only": true, "max_actions_per_hour": 20}
}
```

`<p>` is the built-in `deepseek` provider when the base URL host is `api.deepseek.com`, and
`custom:<base_url>` otherwise (any OpenAI-compatible API). It then execs `nullclaw acp`.

## Note

NullClaw creates `<workspace>/.nullclaw` with mode 0700 on the first prompt. On hosts where the
container uid (10001) differs from the host user, ABB's host-side workspace export may hit
`PermissionError` on that directory. That is the general host-uid issue, not specific to this unit.

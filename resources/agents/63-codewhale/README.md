# Codewhale (ACP)

[Codewhale](https://github.com/codewhale-hq/Codewhale) is a Rust terminal coding
agent. This unit runs its native ACP server headlessly against the runtime's shared
OpenAI-compatible model route.

## Pinned distribution

| Item | Value |
| --- | --- |
| Upstream revision | `fead51eeea0fb6038ea3e30923751b1a1c765b25` (release tag `v0.10.1`) |
| npm package | `codewhale@0.10.1` (see `install/package.json` + lockfile) |
| ACP entry point | `codewhale serve --acp` (stdio) |
| Base image | `node:24-bookworm` |

`install/package.json` and its lockfile are the only installation inputs. ABB copies
them into the ignored `agent/` before the build, and the Dockerfile then runs
`npm ci --ignore-scripts` followed by the package's own installer,
`node node_modules/codewhale/scripts/install.js`.

That installer is what fetches the single native binary and verifies it against the
release's `codewhale-artifacts-sha256.txt`. It is run explicitly — not through the
npm `postinstall` hook — because the hook uses the fail-fast `--optional` form
(15 seconds, one attempt) that can silently defer the download to first launch, and
the agent container admits no route other than the model, so a deferred download
would fail there instead of at build time.

## Model mapping

`bootstrap/launch.py` reads the runtime-owned `ABB_AGENT_MODEL_API_KEY`,
`ABB_AGENT_MODEL_BASE_URL` and `ABB_AGENT_MODEL` and maps them onto Codewhale's
documented route overrides:

| Runtime value | Codewhale variable |
| --- | --- |
| `ABB_AGENT_MODEL_BASE_URL` | `CODEWHALE_BASE_URL` (with `CODEWHALE_PROVIDER=openai`) |
| `ABB_AGENT_MODEL_API_KEY` | `CODEWHALE_API_KEY` |
| `ABB_AGENT_MODEL` | `CODEWHALE_MODEL` |

The key only ever exists in the child environment: it is not written to a config
file, not placed in argv, and scrubbed from error output. `CODEWHALE_TELEMETRY=0`
and `CODEWHALE_NO_UPDATE_CHECK=1` keep both subsystems off the admitted route, and a
disposable `HOME` is created per Case so config, sessions and logs stay writable by
whichever unprivileged uid the runtime selects.

## Deployment shape

- Workspace: `/home/agent/workspace`, empty at start, writable, recreated per Case.
- Permissions: ACP `permission_policy = "allow_once"`; the container is the sandbox.
- Network: no routes in `network/rules.toml`. Only the model route declared in
  `agent.toml` is admitted; everything else reaches ABB's egress observer, is refused
  with 403 and is recorded in `egress.jsonl`.
- Not available in this deployment: MCP servers, skills, plugins, GitHub or automation
  credentials, language servers, and any preloaded project. `Web`, `github`,
  `automation`, `rlm` and `mcp_*` therefore stay deferred and unusable.

## Rebuilding

```bash
# static checks
python scripts/validate_unit_generic.py resources/agents/63-codewhale codewhale

# one local Case (Docker, no KUMA spend)
ABB_RUNTIME_BUILD_TIMEOUT_SEC=3600 .venv/bin/python -m agentbench evaluate \
  codewhale --cases 1 --sdk local --no-view -y --model deepseek-chat
```

The unit is registered as `adapting` / `enabled = false` in `resources/registry.toml`;
`evaluate` only selects enabled units, so enable it for a run and restore the registry
afterwards.

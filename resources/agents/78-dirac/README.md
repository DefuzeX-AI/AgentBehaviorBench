# Dirac native ACP integration

Tracks [#471](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/471).
Runs the official `dirac-cli@0.5.23` package, whose release tag `v0.5.23`
resolves to `dirac-run/dirac@f1847e91e702fa5c058cfb31d339dc5346481b9c`
(Apache-2.0). The source tag is used to inspect native behavior; the runtime
uses the published package, not a locally modified source build.

## Installation

This is a package-based unit with `[source] method="install"`.
`install/package.json` and `install/package-lock.json` pin the official package
and its transitive npm dependencies with integrity hashes. ABB restores these
inputs into ignored `agent/`; the Dockerfile runs `npm ci` there. Neither the
upstream source, the installed package nor `node_modules/` is committed.

Node.js 24 satisfies the release's declared `>=22.13.0 <25.0.0` engine range.
The image also provides Python 3.11, Bash, Git and ripgrep. Lifecycle scripts
are skipped: Dirac already ships its built runtime, and system ripgrep is used
instead of `@vscode/ripgrep`'s optional binary download. No GPU is needed.

## Native configuration

`bootstrap/launch.py` maps runtime-owned `ABB_AGENT_MODEL_*` values to Dirac's
documented `DIRAC_PROVIDER`, `DIRAC_MODEL`, `DIRAC_BASE_URL` and `DIRAC_API_KEY`
environment variables. `openai` selects Dirac's generic Chat Completions
implementation and accepts the exact selected model and base URL; it does not
pin the external service to OpenAI or DeepSeek. The launcher writes no model
configuration or credential file and includes no credential in argv.

The native configuration mapping is in upstream
`src/shared/storage/env-config.ts`; ACP startup and default Act/approval state
are in `cli/src/acp/index.ts` and `cli/src/agent/DiracAgent.ts`. Each ACP process
gets a fresh home, configuration root and data/log paths outside the workspace.
No auto-approve, YOLO or tool-selection flag is supplied. ABB handles individual
native permission requests with `allow_once`.

The default native tools remain registered. External services, MCP servers,
browser executables and remote credentials are not provisioned. The
[Agent Profile](requirement.md) describes this deployment's actual task surface
and network limits. The committed registry stays disabled and `adapting`
pending maintainer review.

Local acceptance artifacts belong under `docs/validation/issue471-dirac/`,
outside the Agent's build context. Official KUMA evaluation and phase-two GT
testing are separate from this integration.

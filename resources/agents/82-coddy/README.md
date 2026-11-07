# Coddy native ACP integration

Tracks [#514](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/514).
Runs the official Linux amd64 release `1.3.42` from
`coddy-project/coddy-agent@82e994b5ca32904412c561002dfda28650632af0` (MIT).

## Source and installation

This is a release-package unit with `[source] method="install"`.
`install/distribution.json` pins the upstream repository, commit, release URL,
platform and SHA-256. ABB materializes it into ignored `agent/` before the
Docker build. The Dockerfile downloads the official archive, verifies its
SHA-256, installs the native binary and checks its version. Do not commit `agent/`.
No upstream business logic or binary is patched.

The release tag resolves to the source revision above. Its Linux release build
uses `CGO_ENABLED=0`; neither a Go toolchain nor a GPU is needed at runtime.
This unit currently supports `linux/amd64` only.

## Model and native runtime

`bootstrap/launch.py` reads runtime-owned `ABB_AGENT_MODEL_*` values and writes
native configuration for one `openai` provider named `abb`. Its model is
`abb/<selected API model ID>` and its base URL is the exact selected runtime URL.
The credential is passed as `ABB_API_KEY`, Coddy's documented provider-name
environment convention, and is absent from the written configuration and argv.
The manifest uses shared selection without a vendor pin. Native model-list
discovery requires the shared `/models` metadata route.

Each ACP process has a disposable home and native session store. The default
Agent mode, native tool registry and `ask` permission state remain in use; ABB
answers native requests with `allow_once`. Filesystem and shell operations run
through Coddy's normal ACP integration. No external MCP server or service
account is configured. The [Agent Profile](requirement.md) describes tools and
the network restrictions of this deployment.

The committed registry stays disabled and `adapting` pending maintainer review.
Local acceptance records, when produced, live outside the Agent build context
under `docs/validation/issue514-coddy/`. They are separate from official KUMA
certification and phase-two GT work.

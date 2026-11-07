# Blade Code native ACP integration

Tracks [#513](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/513).
Runs official npm package `blade-code@0.11.23` (MIT), whose registry `gitHead`
is `echoVic/blade-code@266fd27a2c9bfb2bf83b1e308cceef60cdf220f6`.
The source checkout is used to inspect native behavior; the runtime uses the
published distribution, with no upstream Agent code changes.

## Installation and source

This package-based unit uses `[source] method="install"`.
`install/package.json` and `install/package-lock.json` pin the published package
and transitive dependencies with npm integrity hashes. ABB restores these inputs
into ignored `agent/`, then the Dockerfile runs normal `npm ci --omit=dev`.
The wrapper explicitly approves the locked `better-sqlite3@11.10.0` and
`node-pty@1.1.0` installation scripts for npm versions using script approval.
Do not commit the
installed package, `node_modules/` or ignored `agent/`.

The image uses Node.js 24, which satisfies the native `>=22.19.0` engine range,
and provides Python 3.11, Bash, Git and ripgrep. No GPU is required. Browser
executables, external language servers and remote service accounts are not
installed by this unit.

## Model, workspace and permissions

`bootstrap/launch.py` consumes runtime-owned `ABB_AGENT_MODEL_*` values and
writes non-secret native configuration under a fresh `HOME/.blade/config.json`.
Its custom `abb` channel uses `wireApi="openai-completions"`, the exact selected
model/base URL and `apiKeyEnv="ABB_AGENT_MODEL_API_KEY"`. The configuration
contains only the credential variable's name, and argv contains no credential.
The manifest uses ABB's shared model selection without pinning a provider.

The native contract is documented in upstream
`docs/configuration/config-system.md` and implemented in
`packages/cli/src/config/modelProviders.ts` and
`packages/cli/src/services/pi/PiModelCatalog.ts`. The launcher starts
`blade --acp` in the Case workspace and isolates its home and storage root.

The co-located deployment keeps ABB's advertised file and terminal capabilities,
so Blade selects its native ACP remote services. `bootstrap/acp-compat.mjs`
adapts the following ACP transport boundaries:

- Blade sends a complete shell expression in `terminal/create.command` without
  arguments. ABB treats that field as an executable. The relay sends
  `/bin/bash` with `args=["-c", originalCommand]`, preserving cwd, environment
  and all other request fields. ABB's real terminal executes the command.
- ABB serializes a missing-file read as internal error `-32603`; Blade expects
  resource-not-found `-32002` before creating a new file. The relay normalizes
  that error only for a matching native read request and an actual `ENOENT`
  confirmed in the same workspace. Existing files, other errors and paths
  outside the workspace (including symlink escapes) are not normalized.
- A native `session/prompt` RPC error with code `-32603`, exact message
  `Internal error: Agent turn failed (verification_failed)` and matching
  `data.failureType="verification_failed"` otherwise prevents ABB from judging
  the completed tool/stream evidence. For a tracked prompt only, the relay
  appends a clearly labeled ABB adapter diagnostic and returns ACP
  `stopReason="refusal"`. It preserves the complete original error under
  `_meta["abb/verificationFailure"].nativeError`, with `status="failed"`.
  Previously streamed Agent text stays unchanged and is explicitly unverified.
  The native independent-verification gate, retry limit, model, tools and
  permissions remain enabled and unchanged. This is a judgeable failure result,
  not a verification PASS or an assertion that the user's task succeeded.
  Other error types and untracked responses pass unchanged.

Initialization, task prompts, successful tool results and permission decisions
pass unchanged. Stderr is forwarded unchanged. No native tool is replaced and
neither project's core/source code is patched. This compatibility relay is
part of the integration and should be reviewed alongside its transport tests.
It does not certify interoperability with arbitrary remote ACP clients.

The pinned native ACP entry point does not read the headless-only
`--no-verification-agent` option. Setting that option or inventing a config key
would not disable its gate. The explicit refusal mapping above addresses the
maintainer's failed-verification completion request without patching the npm
distribution or suppressing verification evidence.

A separate local-service attempt was cancelled after native Bash reported
missing sandbox dependencies. An offline probe with those dependencies installed
then confirmed Docker's namespace policy blocks that native sandbox. The final
unit uses the ACP remote services above, without disabling the sandbox or
relaxing Docker security settings. These are integration findings, not GT.

Its default permission mode remains unchanged; ABB answers native requests
with `allow_once`. No YOLO, auto-edit, plan-only or tool-selection flag is set.

Native tools remain registered with their normal capability gates. No external
MCP servers, custom skills/plugins or service accounts are provisioned. The
[Agent Profile](requirement.md) describes the task surface and network limits.
The registry stays disabled and `adapting` pending maintainer review. Acceptance
records belong in `docs/validation/issue513-blade-code/`, outside the build
context. Official KUMA evaluation and phase-two GT are separate tasks.

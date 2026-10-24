# Blade Code onboarding evidence (#513)

The Docker Local SDK run `suite_aef2dac14db848c78efa7f0bb2b3a49c` completed
with Judge `pass`, no evidence gaps and CLI exit 0. The native Agent wrote
`hello.py`, read it back and ran `python hello.py`; the real client terminal
returned `ABB_BLADE_CODE_SMOKE_OK` and `EXIT_CODE=0`. Two native permission
requests were answered `allow_once`. The selected model was
`deepseek/deepseek-flash`, with three observed Agent requests/responses.

The published unit uses official `blade-code@0.11.23` without source edits.
Its unit-local ACP relay translates Blade's complete shell command to Bash
argv and normalizes internal-error responses only when an actual missing file
inside the shared workspace is independently confirmed. Initialization, native
permissions, prompts and successful results pass unchanged. See the unit's
README and transport tests for the complete boundary.

`execution-manifest.json`, `input.json`, `result.json`, `judge-report.json` and
`acp-summary.json` are copied SDK records. `tool-events.excerpt.jsonl` contains
unaltered selected lines from the original ACP stream, omitting model reasoning.
`acceptance-summary.json` is a contributor-generated index with record digests;
it is not an SDK certification. Complete original traces remain local.

The earlier direct remote-service run failed with native `loop_detected` after
repeated ACP callback errors. Its original execution manifest, Judge report and
input result are retained here. A subsequent local-service attempt was cancelled
after repeated sandbox dependency failures; its original host run record is
also included. Installing those dependencies for an offline probe established
that Docker's namespace policy blocks the native local sandbox. The accepted
deployment uses remote services with the documented relay and does not weaken
Docker security. Neither earlier attempt is a GT claim.

Offline verification included six Python launcher checks, six Node transport
checks, clean install-input restoration and a real ABB read/write/terminal check
without model calls. SQLite and PTY native modules were loaded in Docker.
The Agent Profile was validated with the authenticated KUMA catalog context.
No official KUMA Case/Judge call or phase-two GT test was performed. Merge and
maintainer acceptance remain separate from this successful Local Smoke.

## Registry path synchronization

The unit moved from `73-blade-code` to `77-blade-code` when synchronizing with main `962fcac6`. The revision for the maintainer's verification-failure feedback uses `resources/agents/88-blade-code/`; main `0ef4257b` already contains fast-agent at 86 and pi-go at 87. Original acceptance JSON, tool-event excerpts, hashes and recorded historical paths remain unchanged. The relocation itself does not establish a new Agent/model execution.

The subsequent verification-failure compatibility change, focused regression checks and new Docker acceptance records are documented separately in [verification-revision/](verification-revision/README.md). They do not rewrite the historical records above.

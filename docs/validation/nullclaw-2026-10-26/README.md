# NullClaw independent testing — 2026-10-26

Result: no qualifying ground-truth candidate. H3 reproduced in 4 of 10 scheduled independent confirmation trials, below the 7/10 threshold. Five trials completed correctly or repaired the error; one ended before the target path was reached. No formal GT records were created or changed.

## Scope and independence

Issue #453; ABB baseline `8349406e`; pinned native NullClaw source `5f1cade05c19b6ecdfb9565ae3305e892e484da9`. Three source-only hypotheses were preregistered and independently reviewed before paid execution. No existing Agent GT records, prior KUMA defect reports, or upstream issue/fix/PR history informed the hypotheses. The generic native SDK runs with `after_suite=None` so the formal GT matcher is not invoked. No Agent business code, tool permission, model response, or tool implementation was changed.

H1 tests all-occurrence replacement; H2 tests fresh reading of ordinary UTF-8 text beginning with MZ; H3 tests preservation of CRLF during native hashline editing. Original Cases permit legitimate correction and fallback. Each hypothesis uses only its original Case version.

## Infrastructure amendments

1. Initial Docker Hub metadata retrieval failed with EOF; original logs retained. An unchanged retry fetched the compiler and compiled the original target.
2. The original x86_64 Linux-musl binary failed its image version check on the ARM64 host with `rosetta error: bss_size overflow` (exit 133). A minimal outer Docker `TARGETARCH` mapping was applied, retaining the same pinned native source, ReleaseSmall optimization, version and feature defaults. The actual native ARM64 image passed its version check. These results are not x86_64 acceptance evidence.
3. The shared worker unconditionally imports OpenTelemetry but omitted it from its requirements. The independently reviewed `opentelemetry-sdk>=1.30,<2` dependency was added, matching the project's declared version constraint. No observation or security bypass was used.
4. The default host resolver returned reserved fake-IP `198.18.3.247` for the official model hostname. Native SSRF protection correctly rejected that address before HTTP. H1 and H2 startup attempts have zero model calls and are excluded infrastructure attempts. Supported `ABB_DOCKER_DNS=223.5.5.5` was then verified to resolve public addresses in a container and frozen. Model traffic remains captured through the normal interceptor.

Offline, network-disabled checks passed for native version, native architecture, worker telemetry/channel imports and ACP initialize/session-new/EOF. The four relevant worker build/trust tests passed. All earlier failed preparation/run evidence is retained.

## Model and evidence boundaries

The configured provider identifier is `openrouter`, while the actual endpoint is `https://ark.cn-beijing.volces.com/api/v3` and the effective model is `doubao-seed-2-1-lite-260915`. Reported usage comes from the final usage object of each intercepted response, counted once per call. Native tools are represented by NullClaw's XML-style calls/results inside model messages. These are not independent per-tool ACP/OpenTelemetry spans.

The native SDK did not export an independent final filesystem snapshot. Byte comparisons use decoded, untruncated native tool-result contents, with initial `file_write` arguments/acknowledgements and native hashline anchors as precondition evidence. Rendered Markdown line endings and the Agent's completion claims are not the oracle. Cached repeated reads require care: a subsequent acknowledged exact corrective write falsifies the hypothesis even if an older read is replayed.

No local or remote Judge was requested. Host completion and cleanup are checked separately; the preregistered deterministic byte oracle determines hypothesis support. A wrapper-completed `agent_invoke_failed` output is not a passing behavior test; its cause must be classified from evidence. The two pre-pilot DNS failures are infrastructure. Confirmation 09 is a native execution error after nonempty successful model responses, and remains non-support in the denominator.

## Pilot results

- H1: falsified. The Agent's sed attempt was denied by the unchanged allowlist; it used one full-block native `file_edit`, then freshly read all four updated URLs and unchanged remaining bytes. The repeated-match single-occurrence trigger was not reached. Five model calls, 49,656 tokens.
- H2: falsified at task level. Both native file readers incorrectly classified the MZ-prefixed text as a Windows executable, but the Agent used permitted `cat`, freshly read the exact 66 bytes, and correctly answered cedar/37/ready. The intermediate classifier result is not sufficient candidate support. Five model calls, 47,497 tokens.
- H3: candidate supported in the pilot. Initial exact 54-byte CRLF content and hashline anchor L3:3c1 were established. Native `file_edit_hashed` with `new_text="timeout=45"` changed one separator to LF. Final raw read contained 53 bytes and the Agent incorrectly claimed all CRLF was preserved, with no corrective edit. Nine calls, 94,506 tokens. The pilot is excluded from confirmation counts.

## Confirmation protocol

`H3/confirmation-freeze.json` records source/file manifests, all outer install assets, Case/oracle, requirement/profile and registry, ARM64 image identity, actual model, credential identity digest only, DNS, runtime dependencies, native SDK baseline and runner hashes. The batch verifies frozen identities before each invocation. Ten independent new suites use fresh native session/workspace/HOME, one Case/one step, a 600-second Case limit and zero automatic retries. Infrastructure failures are preserved, excluded and replenished; final repairs or correct output falsify the candidate. At least seven supports out of ten scheduled independent trials are required. All ten were completed without removing trial 09 or replacing it with a successful trial. No infrastructure replacement was needed within confirmation.

## Confirmation outcomes

| Trial | Classification | Decisive evidence | Model calls | Tokens |
| --- | --- | --- | ---: | ---: |
| 01 | Falsified | Hashline new_text included CRLF; exact 54-byte fresh read | 8 | 79,886 |
| 02 | Falsified after repair | Native edit restored missing CR (20→21 bytes); new CRLF probe succeeded | 17 | 204,273 |
| 03 | Support | Unrepaired 53-byte read; false preservation claim | 8 | 79,724 |
| 04 | Falsified after repair | Distinct final file_write acknowledged exact expected 54 bytes | 14 | 150,870 |
| 05 | Support | Unrepaired 53-byte read; later attempted old-value edit failed | 10 | 109,055 |
| 06 | Support | Unrepaired 53-byte read; false no-formatting-change claim | 8 | 82,569 |
| 07 | Falsified after repair | Distinct final file_write acknowledged exact expected 54 bytes | 14 | 151,551 |
| 08 | Falsified after repair | Distinct final file_write acknowledged exact expected 54 bytes | 13 | 143,305 |
| 09 | Non-support: trigger not reached | Native NoResponseContent; malformed tool markup prevented fixture creation | 3 | 29,906 |
| 10 | Support | Unrepaired 53-byte read; false 54-byte/all-CRLF claim | 14 | 155,074 |

All ten raw histories and classifications were independently reviewed. In trial 09, all three model responses were HTTP 200, nontruncated and contained nonempty visible text. Malformed `<seed:tool_call>` markup did not establish the fixture; the native parser ended with `NoResponseContent`. This is neither infrastructure exclusion nor a completed successful repair. The frozen batch controller conservatively stopped on the error; a separately documented control invocation verified the unchanged freeze and resumed original trial 10. See `H3/resume-control-note.md`.

Repeated native tool results can be stale. Trial 02's earlier CRLF probe failed, while its later 21-byte CRLF probe succeeded after the acknowledged repair. Trials 04/07/08 used distinct corrective file_write arguments and received successful 54-byte acknowledgements. Those actual repairs take precedence over replayed older 53-byte reads. The native per-turn result cache is consistent with this observation; it was not promoted into an additional hypothesis.

Across three pilots and ten confirmation trials, 13 real-model executions produced **128 intercepted calls and 1,377,872 reported total tokens**. Two earlier DNS-blocked attempts produced zero model calls. All 13 have unique SDK run IDs and successful host cleanup/trace checks; this does not override trial 09's native error. Final frozen file/image/model checks and git diff checks passed. No task containers remain.

No posthoc upstream issue/fix/PR search was performed because the candidate did not qualify. No extra Case version, new hypothesis, prompt adjustment or pass-forcing rerun followed the result.

## Delivery and limitations

Detailed evidence paths in this report refer to the archive root. The repository copy includes this report, preregistration, all three Case/oracle pairs and the small execution/classification ledgers.

The portable ZIP contains original Cases/oracles/preregistration, source **hash maps** (not upstream source), frozen configuration identities, all original execution attempts, model/tool traces, audits, report and export manifest. Known credential values and encoded forms, opaque replay blobs and local absolute paths are sanitized. Each exported file maps to its original and exported SHA-256. It excludes private environment files, upstream source, formal GT directories/gt.json without reading them, and bytecode. CRC and hashes are checked separately from behavioral conclusions. This is a JSON/log evidence archive, not a standalone HTML viewer; redacted helper scripts require local path/private-environment adaptation for replay.

Two implementation files changed, alongside dated validation documents: the outer architecture-aware Docker target and the shared worker telemetry dependency. Native source, Agent permissions, tools, model selection and formal GT lists are unchanged.

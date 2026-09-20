# MiniMax integration remediation progress

Implementation follows [the reviewed design](MiniMax-ABB-Remediation.zh-CN.md).
Each completed change is validated and pushed independently to the fork's main.

## D01 — Result redaction

- Redact Agent output, raw protocol output and errors before the worker's first
  result write. Save a content-free receipt without changing execution status.
- Sanitize the in-memory result passed to KUMA, including alternate invokers;
  sanitizing only the serialized artifact did not protect this boundary.
- Three regressions failed before the fix: successful output, exception text,
  and the actual argument passed to the installed SDK's submit method.
- Existing KUMA packaging tests exposed a separate baseline fixture error:
  `fixture` is not registered with the adapter factory. The same failure was
  reproduced in the original checkout before this change; repair it separately.

Validation: 26 passed, 1 optional container test skipped. Pushed as `67501f8`.

## Verification baseline — KUMA packaging fixture

The synthetic packaging Agent now registers its observe-mode adapter for the
duration of each test. Unknown frameworks remain rejected in production, and
the builder raises if a host-only check accidentally instantiates an Agent.

## Delivery status

D01, D02, D04–D07 and D10 are implemented and validated. D03 now links successful
foreground calls to exact Inputs; failed attempts and background calls retain
only the scope actually observed. D08 enforces workspace provenance, with the
unstructured Case prerequisite limitation below. D09 supports the native optional
credential, but that credential is absent in this environment. D11 results and
the unfinished recovery check are recorded below. Work is closed at the user's
requested stopping point; these remaining limitations are not marked as passes.

## D02 — Preserve request identity

Viewer preserves Case and attempt IDs even when the Input is unknown. Only
record-envelope Input IDs can establish an explicit match; arbitrary prompt
payload fields cannot. Input filtering exposes a separate unassigned-request
list and count instead of implying that absent links mean absent traffic.

Validation: 19 Python tests, 40 frontend tests, production frontend build.
Read-only reindex of the historical run retains the Case on all six model
requests. No historical network evidence was modified.

## D03/B2 and D04 — Emitted tools and separate coverage

Protocol response positions establish explicit emitted-tool relations. Request
history and nested arguments cannot supply IDs. Repeated emissions, duplicate
tool IDs and cross-Case matches are rejected or marked ambiguous. Relationships
never populate framework_span_id. The containing artifact run bounds the index;
available Case, attempt and native session identities further constrain matches.

Historical read-only reindex: 6/6 model HTTP pairs and Case IDs; 3/6 model
requests assigned through 4 exact emitted tools; 0/6 framework links. Three
other HTTP requests have independent coverage. Pure-text/background association
remains the separate B3 deliverable; purpose remains unknown without evidence.
Viewer and terminal review expose these counts independently.

Validation: 25 Python tests, 40 frontend tests and production build.

## D05–D08 — Workspace contract and SDK file evidence

- Explicit workspace and file-evidence policy is shared by runtime, manifest
  validation, programmatic onboarding and SDK capability discovery.
- Generation and execution use identical empty/fixture workspace definitions;
  each attempt has a private writable directory, shared only across its turns.
- PreparedCase now carries an environment SHA-256 through Suite retention and
  recovery. Missing or changed environment provenance rejects execution before
  Agent invocation; original signed Case bytes remain unchanged.
- SDK tracking and diff upload are enabled for MiniMax's actual cwd. Per-step
  file evidence and final bounded changed text files remain after cleanup.
- Viewer Files / Diff exposes file statuses, unified diffs, final text and search.
- SDK snapshots enforce path/size boundaries; exported text additionally passes
  SDK sensitive scanning and ABB's known runtime credential check.

Real official acceptance: `suite_d9b0517ce40f454a82c9fa26d67e01e0`, artifact run
`f2b3eec4fa9f481bb1e098aef2236435`, 3 actual Inputs, Judge pass, cleanup succeeded.
All three file snapshots/diffs complete. First step created input.txt, output.txt
and process.py with diffs; later steps made no changes. All three final files
exported. Fresh Backend capabilities included file_diff; intercepted Judge
multipart logs contained file_diff bodies and unified diff text (not merely
local evidence). The original records stay under results/observe/.

Validation: 80 Python tests passed, 2 optional tests skipped; frontend 40 passed
and production build. Additional Suite/Case/recovery tests exercise the new
prepared environment field. Python 3.10 grammar checked across agentbench.
The real container run caught and resolved filesystem-share and Suite-retention
issues not visible in isolated unit tests.

D08 limitation: matching initial state is enforced, but the pinned official Case
contract has no structured required-file declaration. An arbitrary natural-language
Case can still request a missing prerequisite; this cannot be certified by regex.
See [workspace documentation](../Evaluation-Workspaces.md).

## Verification follow-up — Suite recovery fixtures

The extended 92-case recovery check initially had five failures: three stale
resource-policy assertions reproduced on the unchanged original checkout, and
two mocked descriptors missing the manifest now read by workspace validation.
Updated the bundled-resource assertions to the actual conservative replay policy
and completed the mock manifests. No production replay permission changed.
The resulting Suite/Case/recovery set passes all 91 tests.

## D03/B3 — Native successful-call evidence

The pinned source does have a supported TUI opt-in:
`MAVIS_TUI_LLM_CONTEXT_INSPECTOR=1`. Enabled it in the outer bootstrap. An explicit
ACP evidence_reader hook reads native captures after their documented drain at
prompt completion, exporting only IDs/statuses, never profile contents or model
payloads. Imported MiniMax source is unchanged.

Native provider response IDs join network responses to native session/turn/call
IDs and the owning ABB Input. Duplicate IDs or conflicting owners stay ambiguous;
no timestamp, request-history matching or fabricated framework span is used.

Real pure-text acceptance (local Case/Judge plugin, real MiniMax):
`suite_d6a3efce77cc4166b67de5075d8d6b5d`, artifact run
`0fd128e3784448b8981e9a34ddf2849d`. All three actual turns retained one session,
three distinct native turns and exact response-ID links; zero emitted tools.
The local Judge passed. The separate official file-evidence acceptance remains
the proof for official Backend/Judge integration.

Native limitation: this inspector explicitly records only successful `agent`
logical calls; it discards failed attempts and excludes title/auxiliary calls.
Two background model calls in this run remain unassigned, as required. Extending
coverage to those calls still needs a native observer contract or new revision.

Native-evidence validation: 34 Python tests and 40 frontend tests passed;
production build passed, plus the real three-turn pure-text run above.

## D04/D09 — Native session metadata and optional authentication

Observe mode can capture explicitly configured non-credential native metadata
headers without changing their bytes. MiniMax's existing X-Mavis-Session-Id
retains session scope for background calls; it does not assign a current Input.
Viewer marks optional HTTP failures separately from main model execution.

Source confirms content review reads a managed accessToken or MAVIS_ACCESS_TOKEN,
not MINIMAX_API_KEY. Added optional declared secret forwarding for that supported
native variable. The current environment does not contain this credential, so a
successful review cannot be claimed. Original review/title behavior remains on;
the 401 is retained. This is an external authentication requirement, not a model
routing failure.

Validation: 34 Python tests, 13 dependency-complete interceptor tests and 40
frontend tests passed; frontend production build passed. Native headers,
401/429/503 responses and streamed bytes remain unchanged in interceptor tests.

## D10 — Formal certification

Ran the existing `certify` command against the unchanged saved official Case,
with the complete current integration and three actual Inputs. Certification
succeeded and changed the registry from adapting to ready; no manual status edit.

Suite `suite_1ac5a8288e4648dda9ca48d1ce73b74e`; run
`2efc33d7689845fe8368ed415206b38f`. Judge received/pass, files complete, host
trace validation and cleanup succeeded. All 8 model requests have paired replies,
Case identity and native session identity. All 6 successful main-agent requests
have exact Input links; the 2 background requests retain session-only identity.
Framework LLM spans remain unavailable rather than being fabricated.

Readiness retains the existing technical certification semantics. It does not
claim that optional title review is authenticated, that every generated Case is
well-formed, or that an unrelated service_busy judgment became a pass.

## D04 — Declared background purpose

The native title operation declares only `submit_session_title`. Observe mode
now labels this exact configured tool set as `session_title`, retaining
`declared_tool_set` as evidence. Extra tools or prompt text cannot establish the
classification. Viewer shows purpose separately from session/Input ownership;
the request and response bytes remain unchanged. This does not retroactively
label historical network records or assign title calls to the current Input.

Validation: 18 targeted Python tests, 14 interceptor tests, 40 frontend tests and
production frontend build. The real delayed-title acceptance below independently
verifies the native tool and session behavior; the final purpose-only metadata
addition was validated with interceptor regressions, not another paid run.

## D11 — Acceptance matrix and remaining recovery check

- Four concurrent official Cases, each with three actual Inputs:
  `suite_ab0bab3a196249aa92a5c502992dbeeb`. Four distinct containers and native
  sessions, all four execution intervals overlapped for 13.74 seconds. All 12
  Inputs completed with complete file evidence, host trace validation and
  cleanup. Three Judges passed; one returned terminal `ServiceBusyError`
  (`retryable=false`). It remains a Judge failure, not a fourth pass.
- Real native process against a loopback model with Docker `--network none`:
  401 and 429 retain native retries and finish as `TimeoutError`; injected
  timeout finishes as `TimeoutError`; cancellation as `CancelledError`.
  All child processes are cleaned. Reproduce with
  `tests/acp_fixtures/minimax_native_faults.py` in a staged MiniMax image.
- Real native delayed title crosses into the second foreground turn. Two
  foreground responses link to distinct native turns; the title retains the
  shared native session and is never assigned to the second Input. Reproduce
  with `tests/acp_fixtures/minimax_delayed_title.py` in the same offline image.
- Real LangGraph regression using the local SDK Case/Judge:
  `suite_7793c73c7bba45ec860da22744a8c5b7`, run
  `e09de91cf2bb4167b84000994dafd798`: three Inputs, Judge pass, host trace and
  cleanup succeeded. This is distinct from official Backend acceptance.
- Official Judge timeout exercise:
  `suite_50c9326aa85d4891bb467b042232fac6`, run
  `0b6da3daa17e4ecd88ac0263c09d0ff8`. Three Inputs executed and submitted;
  a one-second operation wait left SDK request
  `kreq_6e7dd59adbad69666d032b623dfccef9` pending. Resume correctly rejected a
  changed runtime source fingerprint because local code was edited during the
  exercise. No provenance was rewritten and no Agent was replayed. Successful
  recovery of that real request remains unverified at this stopping point.

## Repository closeout

Checked both original Agent units `15-claude-agent-acp` and `16-minimax-code`,
including their source trees: neither contains a nested `.git` file/directory.
Their `.gitignore` files are not Git metadata and are retained. Imported source
continues to be local/ignored under the existing unit policy. This delivery
contains this task's remediation changes; unrelated local Agent 15 onboarding
and Viewer navigation edits are left intact in the original checkout.

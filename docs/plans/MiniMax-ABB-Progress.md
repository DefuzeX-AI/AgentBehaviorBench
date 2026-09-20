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

## Remaining

D02–D04: identity projection, tool relationships, native turn/purpose attribution.
D05–D08: shared workspace, SDK file evidence, retained files, Case prerequisites.
D09: optional native review authentication.
D10–D11: real acceptance matrix and certification.

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

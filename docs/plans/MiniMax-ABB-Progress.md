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

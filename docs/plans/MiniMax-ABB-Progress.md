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

## Remaining

D02–D04: identity projection, tool relationships, native turn/purpose attribution.
D05–D08: shared workspace, SDK file evidence, retained files, Case prerequisites.
D09: optional native review authentication.
D10–D11: real acceptance matrix and certification.

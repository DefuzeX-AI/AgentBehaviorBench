# Company evaluation strategy

`profile.md` explicitly selects `CAND-009@1` (Research). This matches the
Company research workflow; it is a test-domain choice, not a guarantee that
every generated task fits Company's native input.

Verified by an authenticated read of the official SDK strategy catalog on
2026-09-09:

- ID: `CAND-009`; version: `1`; display name: `Research`
- Available: true; required capabilities: none
- Maximum steps: 10; supported difficulties: D0, D1, D2
- Catalog release: `ec520b247206bbf939981ddd68b0a5ecbc1dd4e656b0343fe5c818924f208529`
- Catalog default was `BASE-01@1` (General Observable), not Research.

The shared `certify`, `run`, and `evaluate` container worker passes this profile
to KUMA. KUMA validates the exact coordinate against its current catalog during
official Case creation. Do not silently fall back to `auto` if it becomes
unavailable. The current ABB worker still limits each Case to one step.

This change was checked using the SDK profile parser and evaluation build staging.
No Case or Judge call was made to validate this selection end to end.

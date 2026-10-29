# Codewhale #5546: source localization

The retained run confirms **ordinary dependency versions are corrupted between native tool completion and the next model request**. The exact model-bound sanitizer call site is now localized. No new agent execution, binary rebuild, or fix validation run was performed.

## Existing execution evidence

- [Trajectory](../../runs/run-01/trajectory/e5b9a33a5f84415db813de4ca03f7fbf/trajectory.json), step 3, Input `0001`: tool result `call_815783ad7600491f97ae1c55` contains `[redacted]` for both dependency versions. The containing model call is `call_5b45084ad30a4eb78b1af0aa66216d97`, interaction `3bdd812c907023ec34686cc2`.
- [Native ACP events](../../runs/run-01/trajectory/e5b9a33a5f84415db813de4ca03f7fbf/steps/0001/acp-events.jsonl), line 64: the completed tool result with that **same tool call ID** contains `"jsonwebtoken": "^9.0.2",` and `"password-validator": "^5.3.0"`. This proves the model-visible replacement is not merely an agent's allegation or redacted file contents.
- ACP line 2 reports native version `0.9.10`. [process.json](../../runs/run-01/trajectory/e5b9a33a5f84415db813de4ca03f7fbf/process.json) records revision `369868d23e593acd71da51db30058b512175e08d`. The source reviewed below is that historical revision, not the unit's current installation default.
- [Evidence extract](evidence.json) preserves the matched raw event, model message, identifiers, hashes recorded in the trajectory, and relevant provenance.

## Located execution path

| Historical source location | Role |
| --- | --- |
| `crates/tui/src/client.rs:1259-1263`, `prepare_model_bound_request` | Rewrites each `ContentBlock::ToolResult` before projection to a provider protocol. |
| `crates/tui/src/client.rs:628-633`, `redact_model_bound_text` | Masks exact configured secrets, then calls the broad `persistence::redact_secrets` function. This second operation is the wrong policy for ordinary model-bound code. |
| `crates/config/src/persistence.rs:308-331` | Runs the text scrubber line by line and attempts keyed assignment redaction. |
| `crates/config/src/persistence.rs:382-419`, `redact_keyed_assignment` | Matches key substrings against hints, including `token` and `password` declared at lines 234-247. It replaces any nonempty matching value without checking whether the value is credential-shaped. Reconstructing the line also discards the trailing comma. |

Thus `jsonwebtoken` matches `token`, and `password-validator` matches `password`; harmless version ranges become `[redacted]`. The source transformation explains both the observed masking and missing comma. [Client excerpts](whaleClient.json) and [scrubber excerpts](whalePersistence.json) preserve pinned URLs, Git blob IDs, and original line ranges. The similarly named workflow redaction module is not the basis of this localization.

## Independent upstream corroboration

[Issue description](upstream-issue.json) reports the same dependency-version false positive. [Selected upstream fix](upstream-fix.json), commit `2776c214efd52528e0432ecdbbed22df4921d53c`, changes this helper's call from `redact_secrets` to `redact_model_bound_secrets` and adds `model_bound_tool_results_keep_ordinary_code_byte_exact`. The test checks ordinary code and dependency text while still masking actual credential-shaped values. The patch and test were inspected, not executed here. Fix-file line numbers differ from the historical source and are not substituted for the historical fault locations.

## Evidence limits

The trajectory is `partial`: 2 of 12 model calls lack confirmed Input attribution. The defect-bearing step selected above is assigned to Input `0001`, and its tool result is matched by exact ID to native completion. Those unrelated attribution gaps do not erase this observed transformation, but the run must not be advertised as a completely attributed trajectory.

The recorded agent eventually performs the requested edit using a workaround. This GT establishes loss of byte-exact model visibility and impaired read-back; it does not establish inevitable edit failure, corruption of the actual file, or every false-positive example in the upstream issue. The recorded source revision and native version are provenance evidence, not a fresh binary build attestation. The pre-existing `pinned_contains_fix` field is left unchanged and is not used to identify the historical executed version.

[Run integrity](run-integrity.json) records SHA-256 hashes checked before and after this review. The [Case](../../case.verified.json) changes only `Root cause` and `fault location`.

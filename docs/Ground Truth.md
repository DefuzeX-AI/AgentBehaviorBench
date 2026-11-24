# Ground truth discovery

[Guide](Guide.md) · [简体中文](otherLanguages/Ground%20Truth.zh-CN.md)

ABB compares **saved Judge problem summaries** with each GT description. It
scores discovery of known defects, not task completion. Step-level attribution
against reference trajectories was removed with the legacy `trajectory.json`
format and will be rebuilt on the ATIF trajectory.

## Reference Case directories

Keep a saved ABB Case directory for each GT, beside a human-readable
`README.md`: the native `case.json` plus a small `gt.json` description.

```text
ground_truth/
  README.md
  path-truncation/
    gt.json
    case.json
```

```json
{
  "schema": "abb.agent.ground_truth.case.v2",
  "agent_id": "example",
  "id": "path-truncation",
  "summary": "Quoted paths are truncated at spaces",
  "explanation": "The registry loses the suffix of a quoted artifact path.",
  "expected_behavior": "The full quoted path is registered and readable.",
  "observed_behavior": "The registered path stops at the first space.",
  "provenance": {"issue_url": "https://example.com/issue"}
}
```

`expected_behavior`, `observed_behavior`, `task_outcome` and `agent_recovery`
are optional text. Write `explanation` in English, preserving the defect
mechanism, evidence requirements, and exclusions. Paths are resolved locally,
so the GT does not depend on the original Suite. Explicitly distinguish
separate control Cases from defect GTs.

Issue reproductions under `ground_truth/issue_<number>/verify.case.json` are
Cases, not GT descriptions; `python scripts/count_ground_truth.py` counts them.

No archives, file hashes, minimum repetition count or exact source-hash equality
are required. Basic JSON structure, safe paths and bounded file reads remain
checked. GT material remains host-only and excluded from Agent runtime staging.

## Evaluation

`agentbench run` invokes GT comparison after saving the Suite. To compare only
existing results:

```bash
python -m agentbench gt --suite /path/to/suite_directory
```

This command does not generate Cases, execute Agents, or submit to KUMA.
It uses the ABB matcher model: `ABB_GT_BASE_URL`, `ABB_GT_MODEL`,
`ABB_GT_API_KEY`, with the configured model provider as fallback.

1. Compare each saved Judge finding with each GT summary/explanation. A
   different topic or generic failure is insufficient to match a concrete defect.
2. Score 0 for a resolved mismatch, null for pending. A summary match stays
   pending until step attribution is rebuilt on the ATIF trajectory.
   Missing/rejected/incomplete reports and unavailable evidence remain pending.
   A complete pass report with no findings is 0.
3. Deduplicate by GT: any 1 wins, otherwise any pending keeps the GT pending,
   otherwise 0. The final discovery fraction is unavailable while any GT is
   pending. Show matched, unmatched and pending counts and possible score bounds.

Each matcher request is journaled before dispatch. There are no automatic
transport retries. Existing completed or failed/interrupted requests are not
resent. Metadata (file sizes and modification times), protocol and settings
identify stale evaluations; no file content hashes are calculated or validated.
Repeated evaluation of unchanged saved inputs reuses the result. Failed requests
remain pending; the CLI has no implicit retry or force-resubmit path.

Outputs live under `<suite>/ground_truth/evaluations/<id>/`, with
`ground_truth/latest.json` selecting the current result and `ground_truth/calls/`
retaining request journals. Suite and Benchmark views read the same scores;
old human-assessment sidecars are not mixed into the new scoring protocol.
Original Suite events, Agent traces and Judge reports are never rewritten.

## Migration and validation

Legacy `manifest.json`, `matching.json` and ZIP observations must be explicitly
migrated to complete native Case directories with short descriptions. The former
inline `ground_truth.json` format also requires migration. `gt.json` files still
on `abb.agent.ground_truth.case.v1` are rejected until regenerated. Legacy result
files remain historical and are not counted under this protocol.

Relevant checks: `tests/test_ground_truth.py`, `tests/test_gt_matching.py`,
`tests/test_ground_truth_isolation.py`, `tests/test_benchmark_evaluators.py`
and the Suite viewer tests. They cover summary matching, failure/unknown
handling, cache behavior, SDK-scoped counts and runtime isolation.

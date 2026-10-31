# Ground truth discovery

[Guide](Guide.md) · [简体中文](otherLanguages/Ground%20Truth.zh-CN.md)

ABB compares **saved Judge problem summaries first**, then both the GT
reference trajectory and the matching execution's trajectory, step by step. It
scores discovery of known defects, not task completion, and records where in
the trajectory the defect became inevitable. Agent recovery does not erase an
observed defect.

## Reference Case directories

Keep a complete saved ABB Case directory for each GT, beside a human-readable
`README.md`. Copy the native `cases/<agent-key>/<case-index>/` tree, including
`case.json`, generation/publication records when present, and all `attempts/`
files. Preserve conversations, tool payloads, produced files, errors and logs
in their original layout. Beside those raw records every reference attempt
carries its derived `trajectory.json`; the raw records are never replaced by it.

```text
ground_truth/
  README.md
  path-truncation/
    gt.json
    case.json
    publication.json
    attempts/
      <attempt-id>/
        run.json
        trajectory.json        derived step sequence (abb.agent-trajectory.v1)
        steps/...
        logs/...
        replay/...
        ...
```

Generate the trajectory after copying the attempt:

```bash
python -m agentbench trajectory build resources/agents/<unit>/ground_truth/path-truncation/attempts/<attempt-id> --write
```

`agentbench trajectory show DIR` prints the numbered steps so the decisive step
can be chosen. Each Case adds a small `gt.json` description, selects its
reference attempts and annotates the decisive step:

```json
{
  "schema": "abb.agent.ground_truth.case.v2",
  "agent_id": "example",
  "id": "path-truncation",
  "summary": "Quoted paths are truncated at spaces",
  "explanation": "The registry loses the suffix of a quoted artifact path.",
  "expected_behavior": "The full quoted path is registered and readable.",
  "observed_behavior": "The registered path stops at the first space.",
  "reference_attempts": ["actual-retained-attempt-id"],
  "decisive_step": {
    "attempt": "actual-retained-attempt-id",
    "step_id": 4,
    "agent_name": "example",
    "reason": "The read_file call at step 4 uses the truncated path; every later step only retries it."
  },
  "provenance": {"issue_url": "https://example.com/issue"}
}
```

`decisive_step` follows TraceElephant's definition: the earliest step at which
failure became inevitable, attributed with a role-aware and recoverability-aware
rule. If an upstream slip could still have been caught by a later verification
step, the decisive step is the step that missed that opportunity.
`decisive_step.attempt` must be one of `reference_attempts`, `step_id` must
exist in that attempt's `trajectory.json`, and `agent_name` (optional) must
equal the acting component recorded for that step. `expected_behavior`,
`observed_behavior`, `task_outcome` and `agent_recovery` are optional text.

The README explains each Case and its evidence; `gt.json` supplies the short
machine-readable description without duplicating trajectory content. Write
`explanation` in English, preserving the defect mechanism, evidence
requirements, and exclusions. `reference_attempts` selects directories under
that Case's `attempts/`. Paths are resolved locally, so retained historical
absolute paths do not make the GT depend on the original Suite. Keep
supplemental component probes separate from Agent executions and label their
scope. Explicitly distinguish separate control Cases from defect GTs.

No archives, file hashes, minimum repetition count or exact source-hash equality
are required. Version metadata describes provenance; it does not bypass content
comparison. Basic JSON structure, safe paths and bounded file reads remain
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

1. Compare each saved Judge finding with each GT summary/explanation. The first
   model request contains no trajectories. A different topic or generic failure
   is insufficient to match a concrete defect.
2. Only a positive summary match loads the reference trajectories and the
   candidate execution's trajectory (derived on read for historical packages
   without one). Both are rendered step by step with complete model inputs and
   outputs; requests over 3000 characters are shortened to head and tail only
   when the full rendering exceeds `ABB_GT_MAX_BYTES`. The comparison must cite
   actual reference (`<attempt>/<step_id>`) and candidate step IDs and name the
   candidate step at which the defect became inevitable. Context that still
   does not fit remains pending rather than losing inputs.
3. Score 1 for a confirmed discovery, 0 for a resolved mismatch, null for pending.
   Missing/rejected/incomplete reports and unavailable evidence remain pending.
   A complete pass report with no findings is 0. A failed execution may still
   contain sufficient evidence of a defect. Each decision also records
   `localization` (reference and candidate decisive steps, Judge-cited steps,
   `step_match`); it is reported beside the score, not folded into it.
4. Deduplicate by GT: any 1 wins, otherwise any pending keeps the GT pending,
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
on `abb.agent.ground_truth.case.v1` are rejected until they carry a
`decisive_step` and their reference attempts carry `trajectory.json`. Legacy
result files remain historical and are not counted under this protocol. Do not
label a component probe as an Agent run or fabricate missing steps.

Relevant checks: `tests/test_ground_truth.py`, `tests/test_gt_matching.py`,
`tests/test_ground_truth_isolation.py`, `tests/test_benchmark_evaluators.py`,
`tests/test_trajectory_*.py` and the Suite viewer tests. They cover summary
gating, two-trajectory step citations, decisive-step validation, failure/unknown
handling, cache behavior, SDK-scoped counts and runtime isolation.

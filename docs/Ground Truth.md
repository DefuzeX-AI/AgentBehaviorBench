# Ground truth discovery

[Guide](Guide.md) · [简体中文](otherLanguages/Ground%20Truth.zh-CN.md)

ABB compares **saved Judge problem summaries first**, then checks both the GT
reference trace and the matching execution trace. It scores discovery of known
defects, not task completion. Agent recovery does not erase an observed defect.

## Reference Case directories

Keep a complete saved ABB Case directory for each GT, beside a human-readable
`README.md`. Copy the native `cases/<agent-key>/<case-index>/` tree, including
`case.json`, generation/publication records when present, and all `attempts/`
files. Preserve conversations, tool payloads, produced files, errors and logs
in their original layout. Do not flatten the trace into one large JSON file.

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
        evaluation/inputs/...
        channel/...
        replay/...
        ...
```

Each Case adds a small `gt.json` description and selects its reference attempts:

```json
{
  "schema": "abb.agent.ground_truth.case.v1",
  "agent_id": "example",
  "id": "path-truncation",
  "summary": "Quoted paths are truncated at spaces",
  "explanation": "The registry loses the suffix of a quoted artifact path.",
  "reference_attempts": ["actual-retained-attempt-id"],
  "provenance": {"issue_url": "https://example.com/issue"}
}
```

The README explains each Case and its evidence; `gt.json` supplies the short
machine-readable description without duplicating trace content. Write `explanation` in English, preserving the defect mechanism, evidence requirements, and exclusions. `reference_attempts`
selects directories under that Case's `attempts/`. Paths are resolved locally,
so retained historical absolute paths do not make the GT depend on the original
Suite. Keep supplemental component probes separate from Agent executions and
label their scope. Explicitly distinguish separate control Cases from defect GTs.

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
   model request contains no traces. A different topic or generic failure is
   insufficient to match a concrete defect.
2. Only a positive summary match opens the selected reference attempt directories
   and loads both traces for comparison. The comparison
   must cite actual reference and candidate event IDs. Native OTel input/output
   payloads and artifact-capture records are included. Missing payloads are
   disclosed. Overlarge context remains pending rather than silently truncated.
3. Score 1 for a confirmed discovery, 0 for a resolved mismatch, null for pending.
   Missing/rejected/incomplete reports and unavailable evidence remain pending.
   A complete pass report with no findings is 0. A failed execution may still
   contain sufficient evidence of a defect.
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
inline `ground_truth.json` format also requires migration. Legacy result files remain historical
and are not counted under this protocol. Do not label a component probe as an
Agent run or fabricate missing trace events.

Relevant checks: `tests/test_ground_truth.py`, `tests/test_gt_matching.py`,
`tests/test_ground_truth_isolation.py`, `tests/test_benchmark_evaluators.py`
and the Suite viewer tests. They cover summary gating, two-trace citations,
failure/unknown handling, cache behavior, SDK-scoped counts and runtime isolation.

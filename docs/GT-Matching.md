# Ground-truth matching

`python -m agentbench run` matches the saved Suite against GT after execution and
SDK judging, before the viewer's post-run menu. Agents without GT are skipped
without model calls. Original execution results, SDK verdicts and human
`assessments.json` records are never rewritten. An error in matching does not
erase execution results or change the execution exit code; inspect the GT panel.

Use `python -m agentbench run --sdk kuma --agent autoresearch-agents -y`
to run one enabled, ready Agent without changing the registry. Repeat `--agent`
to select several. Case and step counts still come from the registry.

To evaluate a saved Suite without re-running agents:

```powershell
python -m agentbench gt --suite C:/path/to/results/suites/suite_example
```

The separate `gt` command creates a new evaluation; it does not resume or reuse
prior model answers. This initial implementation uses all saved attempts,
including retries. Fix retry/case/step budgets before comparing methods.

## Rules and review

Each Agent retains its original `ground_truth/manifest.json` and observations.
`ground_truth/matching.json` contains versioned conditions bound to the original
defect hash. The 15 supplied rules are drafts awaiting human scope review. They
do not establish that the original references were reviewed by a human. Changes
to GT invalidate the binding. Missing rules produce unknown, not a negative.

Rules use source revision applicability. Current drafts are provisional across
model configurations and retain the reference model configuration for review;
they do not claim the defect generalizes to every model or environment.

Stage one judges execution evidence only. Stage two asks whether the original
method's report recognizes that same reproduced defect. Every decisive condition
must cite saved candidate evidence; a reference trace or generic `issue` label
is insufficient. Rules may contain narrower criteria than the defect title.

All automatic scores remain **provisional**. Human rule review and human review
of scored execution matches are separate activities; this version does not
automatically publish a human-confirmed score. Review records should identify
the exact GT/rule/evaluation hash and the evidence considered.

## Provider and artifacts

Uses ABB model-provider resolution and the existing OpenAI-compatible model
transport. Optional `ABB_GT_BASE_URL`, `ABB_GT_MODEL`, `ABB_GT_API_KEY` override
the target. Credentials stay on the host. The local Judge prompt is not reused.
`ABB_GT_MAX_BYTES` (default 240000) limits candidate evidence; overflow is unknown,
never silent truncation. `ABB_GT_MAX_CALLS` (default 200) limits logical matching
calls; each transport call may retry up to three times. Provider failures and
budget exhaustion remain unknown. Raw model replies and sanitized requests are
saved even when response validation fails.

Evidence readers use the viewer's identity-checked artifact catalog and common
execution input/result/trace files, without importing KUMA. Evidence unavailable
in those files (including unresolved external payloads or tool capture gaps)
must result in unknown. This is not a guarantee that all SDK formats are complete.

Results are saved under `<suite>/ground_truth/evaluations/<id>/`, with a live
`latest.json` for the Suite view. New Suite events mark an old evaluation stale.
The original benchmark overview's explicit assessment statistics stay separate.

## Scores

For a fixed set of applicable defects, `r_g` is one if any saved execution
reproduces defect g. `h_g` is one if an execution both reproduces it and its own
method report recognizes it. Duplicate hits count once per Agent/defect.

- Trigger coverage: `sum(r_g) / N`.
- Conditional recognition: `sum(h_g) / sum(r_g)`; N/A when no defect is triggered.
- Full discovery coverage: `sum(h_g) / N`.

For fully resolved results, full discovery = trigger coverage × conditional
recognition. Unknowns produce score bounds `[confirmed/N, (confirmed+unknown)/N]`,
not a point estimate. Bounds are not statistical confidence intervals. Agents
without GT and incompatible source revisions are listed separately. Per-Agent,
micro and macro trigger/discovery values are retained in JSON. A completed
evaluation may still contain unknown outcomes; completion is not correctness.

Before paper-level scoring, independently annotate positives, near misses and
incomplete evidence, separate prompt development from validation by defect, and
measure precision/recall and abstention. The retained reference cases alone do
not validate matching of new cases.
# Eligibility review

`ground_truth/reviews.json` stores version-bound eligibility decisions separately
from original manifests and observation archives (`abb.gt.reviews.v1`). Each entry
contains `ground_truth_id`, `ground_truth_sha256`, `decision`, `reason`,
`reviewed_by`, and `reviewed_at`. `excluded` and `needs_review` are omitted from
matching calls and score denominators; they are not negative matches. `approved`
restores eligibility after human review. Existing units without this sidecar keep
their legacy eligibility; automatic matching results remain provisional.

The Suite summary snapshots the current manifest/rule/review configuration hash.
Changing these inputs makes earlier evaluations stale in View. Archived original
evaluations and reproduction evidence are retained. Native-contract audits in
`ground_truth/native-audit.json` are supporting review material, not human approval.


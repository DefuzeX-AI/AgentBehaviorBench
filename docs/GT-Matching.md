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
prior model answers. It uses all saved attempts, including retries.

## Protocol `summary-trajectory-attribution-v3`

Each GT Case is a `gt.json` (`abb.agent.ground_truth.case.v2`) beside the
complete retained reference attempt(s). Every reference attempt carries its
derived `trajectory.json`; its `decisive_step` names the reference attempt and
the step at which the known defect made failure inevitable (the earliest such
step, judged with the role-aware and recoverability-aware rule of
TraceElephant: a missed verification opportunity is the decisive step, not the
earlier upstream slip). See [Ground Truth](Ground%20Truth.md) for the file
layout and [the trajectory contract](../agentbench/trajectory/README.md) for
what a step contains.

1. **Summary stage.** Each saved Judge finding is compared with the GT summary
   and explanation. No trajectory travels with this request. A different topic
   or a generic failure is not a match.
2. **Trajectory stage.** Only a positive summary match loads the reference
   trajectories and the candidate execution's trajectory. Historical packages
   without a saved `trajectory.json` are derived on read and flagged
   `derived_on_read`. Both sides are rendered in the same mode: `full` first;
   `truncate_middle` when the request would exceed `ABB_GT_MAX_BYTES` (model
   inputs over 3000 characters keep their head and tail, outputs stay whole).
   Nothing is rendered without inputs: a comparison that still does not fit
   stays pending. The matcher must cite `reference_step_ids`
   (`<attempt>/<step_id>`), `candidate_step_ids` and the
   `candidate_decisive_step`; citations are validated against the steps that
   were actually supplied.
3. **Score.** 1 for a confirmed discovery, 0 for a resolved mismatch, null for
   pending. Missing, rejected or incomplete reports, unavailable evidence and
   oversized context remain pending. A complete `pass` report with no findings
   is 0. A failed execution may still contain sufficient evidence of a defect.
4. **Localization.** Each decision records `localization`: the reference
   decisive step, the candidate decisive step the matcher identified, the steps
   the Judge finding cited (when its report names `step_ids`) and `step_match`.
   `step_localized` counts defects whose Judge citation contains the candidate
   decisive step. It is reported beside, never inside, the discovery score;
   reports that cite no steps are `not scored`, not wrong.
5. Deduplicate by GT: any 1 wins, otherwise any pending keeps the GT pending,
   otherwise 0. The discovery fraction is unavailable while any GT is pending;
   bounds `[confirmed/N, (confirmed+unknown)/N]` are shown instead.

Each matcher request is journaled before dispatch. There are no automatic
transport retries. Existing completed or failed/interrupted requests are not
resent. Evaluations saved under the previous protocol report `legacy` and must
be re-run. GT units whose `gt.json` is still v1 or whose reference attempts have
no `trajectory.json` are reported as warnings and left unassessed:

```bash
python -m agentbench trajectory build resources/agents/<unit>/ground_truth/<case>/attempts/<id> --write
```

## Provider and artifacts

Uses ABB model-provider resolution and the existing OpenAI-compatible model
transport. Optional `ABB_GT_BASE_URL`, `ABB_GT_MODEL`, `ABB_GT_API_KEY` override
the target. Credentials stay on the host. The local Judge prompt is not reused.
`ABB_GT_MAX_BYTES` (default 8 MiB) limits one matcher request;
`ABB_GT_MAX_CALLS` (default 200) limits logical matching calls. Provider failures
and budget exhaustion remain pending. Raw model replies and sanitized requests
are saved even when response validation fails.

Results are saved under `<suite>/ground_truth/evaluations/<id>/` (or beside
the Agent's results for managed layouts), with `tasks/NNNNNN/trajectories.json`
holding both trajectories as supplied, the render mode and the decisive step,
and a live `latest.json` for the Suite view. New Suite events or changed GT files
mark an old evaluation stale.

## Review

All automatic scores remain **provisional**. Human review of scored matches is
a separate activity; `ground_truth/reviews.json` (`abb.gt.reviews.v1`) stores
version-bound eligibility decisions (`excluded`, `needs_review`, `approved`)
that are omitted from matching calls and score denominators without counting
as negative matches. Before paper-level scoring, independently annotate
positives, near misses and incomplete evidence, separate prompt development
from validation by defect, and measure precision/recall and abstention. The
retained reference cases alone do not validate matching of new cases.

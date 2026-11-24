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

## Protocol `summary-v4`

Each GT Case is a `gt.json` (`abb.agent.ground_truth.case.v2`) beside its
original `case.json`. See [Ground Truth](Ground%20Truth.md) for the file layout.

1. **Summary stage.** Each saved Judge finding is compared with the GT summary
   and explanation. A different topic or a generic failure is not a match.
2. **Score.** 0 for a resolved mismatch, null for pending. A positive summary
   match also stays pending: step-level attribution compared legacy
   `trajectory.json` documents, was removed with that format, and will be
   rebuilt on the ATIF trajectory. Missing, rejected or incomplete reports and
   unavailable evidence remain pending. A complete `pass` report with no
   findings is 0.
3. Deduplicate by GT: any 1 wins, otherwise any pending keeps the GT pending,
   otherwise 0. The discovery fraction is unavailable while any GT is pending;
   bounds `[confirmed/N, (confirmed+unknown)/N]` are shown instead.

Each matcher request is journaled before dispatch. There are no automatic
transport retries. Existing completed or failed/interrupted requests are not
resent. Evaluations saved under an earlier protocol report `stale` or `legacy`
and must be re-run. GT units whose `gt.json` is still v1 are reported as
warnings and left unassessed.

## Provider and artifacts

Uses ABB model-provider resolution and the existing OpenAI-compatible model
transport. Optional `ABB_GT_BASE_URL`, `ABB_GT_MODEL`, `ABB_GT_API_KEY` override
the target. Credentials stay on the host. The local Judge prompt is not reused.
`ABB_GT_MAX_BYTES` (default 8 MiB) limits one matcher request;
`ABB_GT_MAX_CALLS` (default 200) limits logical matching calls. Provider failures
and budget exhaustion remain pending. Raw model replies and sanitized requests
are saved even when response validation fails.

Results are saved under `<suite>/ground_truth/evaluations/<id>/` (or beside
the Agent's results for managed layouts), with a live a live `latest.json` for the Suite view. New Suite events or changed GT files
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

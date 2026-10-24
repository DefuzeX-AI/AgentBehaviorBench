# DeerFlow Ground Truth

This directory contains three complete ABB Case result directories copied from
existing runs. Each copy retains `case.json`, `generation.json`,
`publication.json`, and the entire historical `attempts/` directory. The Agent
was not rerun, and nothing was resubmitted to KUMA. Each Case's `gt.json` contains
a concise defect description and reference attempt IDs; it does not embed or
duplicate the traces.

| Case directory | Defect | Evidence in the reference execution | Agent recovery and task outcome |
| --- | --- | --- | --- |
| [issue-7303-artifact-path](issue-7303-artifact-path/) | [#7303](https://github.com/bytedance/deer-flow/issues/7303): artifact paths containing spaces are truncated | A path containing spaces is created; ArtifactCapture registers a truncated path; reading it fails; reading the full path returns CHECKPOINT-7303. | The full-path fallback succeeds, but the Agent subsequently retries truncated references and eventually reaches the recursion limit. |
| [issue-7302-sql-columns](issue-7302-sql-columns/) | [#7302](https://github.com/bytedance/deer-flow/issues/7302): JSON export loses values for duplicate SQL column names | Two columns named id contain 1 and 2; JSON retains only id=2. A control with distinct column names preserves both values. | The Agent identifies the lost value and compares other formats, then eventually reaches the recursion limit. |
| [issue-7235-podcast-exit](issue-7235-podcast-exit/) | [#7235](https://github.com/bytedance/deer-flow/issues/7235): failed podcast generation returns exit code 0 | Generation reports an error and produces no MP3, but the process returns 0. An invalid-argument control returns 2. | The Agent correctly identifies the failure and completes the diagnostic task; audio generation is not recovered. |

## Inspecting the evidence

Each Case's `case.json` contains the task inputs.
`attempts/<id>/run.json` records execution status.
`attempts/<id>/evaluation/inputs/` retains the original inputs, outputs, OTel
traces, and payloads. Other directories, including `channel/`, `replay/`, and
`agent-output/`, retain their original structure. The `evidence/` directory
contains three existing component-probe results; these are not three Agent runs.

The Cases originate from slots 0, 2, and 3 of
`suite_4a9ae480fe9348eca2f14d832176637c`. The no-space control for #7303 is a
separate Case in slot 1 of that original Suite and remains in the original
results directory. It is not a separate ground-truth defect. This directory
contains only the Cases corresponding to the three defects.

Historical absolute paths are retained for provenance only. ABB reads the copied
artifacts through local relative paths and does not depend on the original
results directory. These retained reference Cases use the historical layout;
new runs use the layout described in [Result storage](../../../../docs/Result-Storage.md).

## How ABB evaluates matches

ABB first compares existing Judge issue summaries against the `summary` and
`explanation` in `gt.json`. Only after a summary match does it load the original
local traces identified by `reference_attempts` and compare them with the current
execution's traces. A confirmed defect match scores 1, a clear mismatch scores 0,
and insufficient evidence remains unresolved. Recovery outcomes are recorded
separately.

Execution success or failure alone does not determine a ground-truth match.
Matching does not rely on ZIP archives or file hashes.

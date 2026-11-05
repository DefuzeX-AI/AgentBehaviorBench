# Experiment 3: Issue repair validation

`agentbench exp3` exports an editable historical project and checks a submitted
source directory using the original GT reproduction Case. The repair agent edits
the exported code; ABB executes and assesses it. The command does not generate
repairs itself.

## Export a project

For source-only exports, add `--noRun`:

```powershell
python -m agentbench exp3 genProject nanocoder --issue 1343 --output "C:\experiments\nanocoder-1343" --noRun
```

This mode fetches the exact GT commit from the Agent's `source.repository` and
exports `source/` plus `issue.json` without preparing a runnable Agent. It requires
no Dockerfile, historical build recipe, runtime or launch configuration, including
for install and bundled Agents. Provenance records the repository and commit;
`base_target` is null because no executable target was prepared. A valid full GT
commit and repository URL are still required. This mode recursively exports
submodules at the gitlink commits recorded in each historical tree; submodule
branch settings do not select versions. Relative repository URLs and GitHub-style
`git@host:path` URLs are resolved to HTTPS. Internal relative symbolic links are
preserved, including dangling links; escaping or cyclic links are rejected.
Windows needs symbolic-link support (Developer Mode or appropriate privileges).
Git LFS pointers remain unsupported. Without the flag, the
existing historical target preparation remains in effect. Neither export mode
runs an Agent, builds an image, or calls a model.

Source-only provenance records each submodule's path, repository and full commit.
Its `abb.export-tree.v1` digest hashes all exported file bytes, directory paths
and symbolic-link targets without dereferencing links. Source-only archives use
a separate cache for recursive trees; runtime preparation keeps its existing
source restrictions.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
python -m agentbench exp3 genProject nanocoder --issue 1343 --output "C:\experiments\nanocoder-1343"
```

`--output` must be a new absolute directory outside ABB. Its only top-level
entries are `source/` and `issue.json`. Source comes from the exact full
`commit_version` in `verify.case.json`; missing or invalid versions fail, with no
default-version fallback. The exported source is the original commit archive,
without Git history or ABB installation overlays. `issue.json` contains exactly
the definition's `issue` object, not root cause, fault locations, expected/defect
annotations, reproduction steps or reference trajectories. If the Issue object
contains only metadata and a title, the export does not invent a full report.

Generation reuses historical target preparation and verified source archives.
It makes no model calls and does not build Docker images. A generated project is
not proof of successful execution. Git units and install units with a declared
historical source recipe are supported. Unsupported preparation fails explicitly.

Host provenance is saved separately under `<ABB-parent>/outputs/exp3/projects/`,
or `--records-dir`. It records the requested Issue, baseline target, export path
and source digest. It stays outside both the exported project and ABB repository.
Existing export directories are never overwritten. An interrupted export may
leave a partial directory; use a new destination or review it before removing it.

## Validate edited source

```powershell
python -m agentbench exp3 run nanocoder --issue 1343 --source "C:\experiments\nanocoder-1343\source"
```

`--runs` defaults to 3 and accepts a positive integer. It counts repeated
executions of the same submitted repair, not repair attempts. Change the code and
invoke `run` again for another repair submission. `--model` selects the target
model through the existing provider rules. `run` does not call a Judge.
`--timeout` applies to each Case execution. Use `--env-file`
for an explicit host environment file.

At invocation, ABB freezes `verify.case.json`, its validated reference
trajectories, and one native Case whose ordered inputs are exactly the GT
`steps`. Each input remains in the same session and task workspace. Baseline and
repair executions receive identical Case content and model settings.

ABB takes one source snapshot before execution. The snapshot replaces the whole
Agent source tree, so deleted and renamed upstream files stay deleted. Existing
ABB installation overlays are applied with conflict checks. The default Agent
unit and cached historical baseline remain unchanged. A new target records its
base commit, submitted/effective source hashes and full target digest. Its local
`bundled` preparation prevents upstream source restoration while preserving
normal installation-input checks. Historical source build recipes are retained,
including for install units; validation cannot silently run a published package.

The existing Docker runtime incorporates the selected source and compiles it
where required. Its content-based image cache may be reused. Exp3 does not use
an old image merely because the Agent name or base commit is unchanged.

Each invocation first runs the unmodified baseline once to confirm that the
frozen Case can reproduce the issue in the current environment. This is
**additional to** the requested repair runs: the default means one baseline
execution plus three repair executions. All repair runs are attempted even if
an earlier one fails or remains unknown. Each starts a fresh session and task
workspace, with no automatic target retry. Run experiment processes serially on
the same Docker daemon, as existing image coordination is scoped to one Suite.

## Results and evidence

Execution finishes with `NOT_JUDGED`, which is distinct from a Judge's `unknown`.
Run the third phase separately using saved evidence only:

```powershell
python -m agentbench exp3 judge auto --experiment "C:\experiments\exp3_run" --model openai/gpt-4.1-mini
python -m agentbench exp3 judge export --experiment "C:\experiments\exp3_run" --output "C:\experiments\review-new"
# Fill reviewer and decisions in review.json, preserving the manifest.
python -m agentbench exp3 judge import --experiment "C:\experiments\exp3_run" --input "C:\experiments\review-new\review.json"
```

All paths above must be absolute. `auto` accepts `--env-file`; `--model` overrides
only the Judge model on the configured provider. Without it, the shared provider's
model is used. Neither manual command needs credentials. Export includes complete
trajectories, frozen references and readable Judge inputs; it requires a new output
directory. Import requires all decisions, reviewer identity, unchanged evidence
hashes, valid step IDs and exact candidate quotes. Citation validation cannot
prove a human's interpretation is correct.

Each automatic or manual judgment is appended under `judgments/<id>/`, with its
own verdict, source, timestamp and provenance. Automatic journals retain prompts
and responses. Existing execution results and previous judgments are unchanged.
`result` returns the execution record plus all judgments; it never silently selects
one as authoritative. Legacy complete Exp3 artifacts can be judged the same way.
Missing evidence yields `unknown`; changed evidence hashes are rejected.

The separate automatic assessment uses the repair-specific Judge protocol. It receives the canonical
`defect`, `Root cause`, `expected`, historical reference trajectories, and the
candidate trajectory. It does not receive the submitted source tree or patch.
Historical and candidate steps have distinct citation IDs. The Judge examines
actual calls, arguments, results, and responses and returns `bug_exist`,
`bug_fixed`, or `unknown`. A fix requires observed evidence that the relevant
operation works and the original Case's expected behavior is satisfied. An
unrelated failure, unexercised operation, or missing relevant outcome is
`unknown`. A decisive label requires an existing candidate step and an exact
output excerpt; `bug_exist` also requires a historical reference citation.
The bounded full-context request, one evidence-correction call, raw response,
usage, and journal behavior are shared with the existing oracle. Citation checks
confirm attribution, while semantic interpretation remains a model judgment.

- `PASS`: the baseline returned `bug_exist`, and all requested repair executions
  completed and returned `bug_fixed`.
- `FAIL`: any repair execution returned `bug_exist`.
- `UNKNOWN`: no decisive repair failure was established, but baseline
  reproduction, execution, expected behavior or oracle evidence remain unresolved.

This scope is `original_reproduction_case`. A pass does not claim that unrelated
functionality or the entire project's regression suite was tested. The LLM
oracle retains the reliability limitations documented in
[Experiment 1](Experiment1.md); inspect evidence before publishing repair rates.

Real container controls for Nanocoder issue 1343 reproduced the defect at commit
`59874391f939bdfe93c273a10d23a7a94009edd1` and showed successful matching after
a local source repair. The configured `openai/gpt-4.1-mini` oracle nevertheless
classified that repaired execution as a defect. Replaying the exact recorded
initial prompt once with `anthropic/claude-opus-4.6`, changing only the model,
returned `match=false` with valid citations to the two successful tool calls.
This is a single saved-trace comparison, not an end-to-end Exp3 acceptance run
with that model or an estimate of oracle accuracy. No default model was changed.

Progress is printed to stderr; stdout is JSON. Results default to the short path
`<ABB-parent>/r/exp3/exp3_<id>/` to reduce Windows path-length problems. Override it
with `--results-dir` outside ABB and the submitted source. The directory contains
the frozen Case/definition/reference, target snapshot and provenance, baseline
and per-run Suites, raw traces, trajectories and `result.json`. Separate judgments contain oracle journals.
Each run records execution and total time. A failure still preserves available
artifacts, including unresolved outcomes.

Read saved results without credentials or model calls:

```bash
python -m agentbench exp3 result --experiment /absolute/path/to/exp3_run
```

Exit zero means the command produced a result, including `FAIL` or `UNKNOWN`.
Configuration/preparation errors return nonzero; interrupted or failed runs retain
their partial result when the result directory was already created. Inspect
`verdict`, `status`, `baseline`, `trials`, and `completed_runs` for the outcome.

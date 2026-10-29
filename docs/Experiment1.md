# Experiment 1: behavioural failure detection

`agentbench exp1` executes externally generated Cases against one Issue's pinned
Agent version. Each Case runs once, is assessed by an independent trajectory
oracle, and consumes one test execution. Execution stops at the first confirmed
hit. The command does not generate Cases or require a testing-agent diagnosis.

## Input and invocation

Pass an explicit Issue number and the **absolute path** to one JSON file:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
python -m agentbench exp1 run nanocoder --issue 1343 --cases "C:\experiments\nanocoder\cases.json"
```

On Linux:

```bash
python -m agentbench exp1 run nanocoder --issue 1343 --cases /work/experiments/nanocoder/cases.json
```

The file must use the existing `abb.cases.v1` collection format and contain
**1 through 50 Cases**, in execution order. Case IDs must be unique.

```json
{
  "schema": "abb.cases.v1",
  "cases": [
    {
      "case_id": "test-001",
      "inputs": [
        {"input_id": "step-1", "payload": "First user message"},
        {"input_id": "step-2", "payload": "Follow-up user message"}
      ]
    }
  ]
}
```

`inputs` are the steps of a Case. They execute sequentially in one session and
workspace. Each subsequent Case starts a fresh session and workspace initialized
from the configured empty state or fixture. One multi-step Case is one test.
A failed input ends that Case through the existing native executor.

There are no `--tests`, `--workers`, or `--case-dir` options in this protocol.
The budget is the number of supplied Cases; neither execution nor automatic
retries multiply it. `--timeout` applies to each Case, and `--model` selects the
target model subject to its existing provider constraints. `--results-dir`
changes the output parent; by default it is `<case-file-parent>/results/`.
On Windows, use a short `--results-dir` path: the nested evidence layout can
exceed the system's path-length limit.
Run separate experiment processes serially on the same Docker daemon. Image
coordination currently covers one Suite; concurrent processes can race while
building or cleaning up the same content-addressed image.

Optional `--prompt-template` and `--scenario-file` retain the upstream generation
context. Use fresh testing-agent sessions when generating Cases and keep Issue
reports, reference trajectories, existing results and GT out of their context.
Every Issue for the same Agent receives the same Agent-level scenario. Issue
selection belongs to the host runner, for version preparation and assessment.
Only the submitted Case and public Agent Profile reach the target executor.

## Historical version

The selected `ground_truth/issue_<number>/verify.case.json` must contain a full
40-character `commit_version`, expected behaviour and defect definition, with
validated reference trajectories under `runs/*/trajectory/*/trajectory.json`.
Missing or invalid revisions fail before execution; there is no default-version
fallback. The plan freezes the Case collection, reference and prepared target.

The existing `EvaluationService.prepare` acquires the exact historical source.
Git units reuse their build recipe. Install units need a declared historical
source-build recipe; Nanocoder already supplies one. Unsupported preparation or
incompatible historical builds fail explicitly. Cached source/build artifacts
may be reused, while each Case's session and workspace remain independent.
The default registration and Agent unit are not modified.

## Execution, assessment and output

Cases execute in array order. After each execution, ABB saves its trajectory and
timing, assesses it, and persists the result before continuing. Progress goes to
stderr; stdout contains the final machine-readable JSON.

- `hit: true`: actual execution triggered the specified defect. Stop and return
  `score: 1`, `first_hit` (the one-based execution index), `matched_case` (the full
  original Case, including every input) and `matched_case_path`.
- `hit: false`: evidence supports absence of the target failure. Continue. If all
  supplied Cases are negative, return `score: 0` with no matched Case.
- `hit: null`: infrastructure, oracle or evidence problems prevent a decision.
  Retain the reason and continue. Without a confirmed hit, unresolved executions
  keep the final score null; they never become automatic negatives.

The oracle uses the default OpenRouter model and endpoint, independently of the
target-model override. It must cite valid execution steps. Predicting a defect,
producing an unrelated failure, or describing a reproduction is not a hit.
Subsequent recovery does not erase a demonstrated trigger. Oversized evidence
stays inconclusive instead of being truncated.

The oracle first reads Case/Input identities, coverage diagnostics, warnings,
step status, recorded evidence identifiers, user inputs, observed model responses
and tool logs. It can request full context once when the defect depends on
request content, file changes or other omitted fields.
Repeated context is represented with lossless references; stored trajectories
remain complete. A positive verdict must quote actual output from its decisive
candidate step. An invalid citation or observation permits one recorded correction
using candidate evidence. Transport failures are never automatically retried.
Initial, context and correction requests and their usage are retained separately.

Trajectory `partial` describes derivation limitations, not the detection result.
The oracle assesses whether the available Case evidence is sufficient for the
specific Issue. Missing Input attribution alone need not prevent a Case-level
negative; absent required responses, tool outcomes or ownership information still
require null. An observed trigger remains valid when unrelated evidence is
missing. The oracle must explain relevant gaps, and no code maps warning text,
Agent names, Issue numbers or prompt similarity to a verdict. Stored trajectory
status and associations are preserved. Oracle protocol v4 separates this policy
from cached decisions made under the earlier blanket partial-negative rule.

The current oracle remains experimental. Expanded validation with
`openai/gpt-4.1-mini` covered 13 targeted scenarios with three judgments each:
20 of 39 decisions matched the reviewed expectation, 9 were semantic
misclassifications, and 10 failed evidence citation validation. Failures included
treating hypothetical error text as an observed trigger, overlooking necessary
preconditions, and treating missing outcomes as negatives. Citation failures
remain unresolved results even when a trajectory contains the target failure.
This debugging sample is not a benchmark accuracy estimate. Review the saved
evidence before using these verdicts for reported Detection@k results.

Each experiment retains `plan.json`, frozen references, per-Case execution and
assessment records, native Suites, full oracle journals, assessment snapshots,
and `result.json`. The selected Case is also saved as `matched-case.json` under
its assessment directory. Raw evidence and negative or unknown outcomes remain
available. Preparation, execution and assessment times are recorded separately;
missing token usage is not invented.

## Detection@k

Detection@k is the fraction of Issues with at least one confirmed hit in their
first k **Case executions**, for k = 1, 5, 10, 20 and 50. A Case's input count
does not change this unit. Results use input order, not completion order.

For example, if the second Case hits, Detection@1 is 0. Detection@5 is 1 when
the submitted budget is at least 5, even though early stopping skipped Cases
3 onward. Cutoffs above the submitted budget are `outside_budget`, not zero.
Unknown evidence leaves the affected score pending, with lower and upper bounds
that retain every selected Issue in the denominator.

Read saved results without credentials or model calls:

```bash
python -m agentbench exp1 result --experiment /absolute/path/to/exp1_run
```

Repeat `--experiment` to aggregate explicitly selected, distinct `(agent, issue)`
pairs. Duplicates are rejected. If submitted budgets differ, the common reporting
budget is their minimum; Issues with smaller budgets are never silently dropped.
Select experiments from the same testing-agent configuration and trial yourself;
this interface cannot observe how the external testing agent generated its Cases.

```bash
python -m agentbench exp1 result --experiment /path/to/run_a --experiment /path/to/run_b
```

## Reassessment and compatibility

```bash
python -m agentbench exp1 match --experiment /absolute/path/to/exp1_run
python -m agentbench exp1 match --experiment /absolute/path/to/exp1_run --retry-failed
```

`match` reuses frozen inputs/references and saved trajectories. It never executes
the target or resumes skipped Cases. Completed identical oracle calls are cached;
`--retry-failed` permits retrying failed/interrupted oracle calls only. For v2,
the configured oracle model and endpoint must match the frozen plan. Interrupted
v2 experiments can be reassessed, with missing tests remaining unresolved.
Execution and reassessment share a lock to prevent concurrent writers.

New experiments use `abb.exp1.v2` with `execution_mode: ordered_cases` and
`metrics_unit: case_executions`. Saved `abb.exp1.v1` experiments remain readable
and matchable using their original ordering and round semantics. They cannot be
mixed into v2 aggregation. Exit zero means a result was produced, including a
negative or partial result; inspect `score`, `status`, and metric availability.

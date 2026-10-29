# Experiment 1: behavioural failure detection

`agentbench exp1` executes externally supplied Cases and measures whether they
trigger an Issue's reported failure. It does not generate Cases, request a
testing-agent diagnosis, invoke a Judge, or open the viewer.

## Input

Provide one directory per Issue, containing N source Cases: numbered JSON
files, or an `abb.cases.v1` collection named `cases.json`. Do not mix formats.
N is inferred from the inputs; `--tests X` specifies only the number of rounds.
Each round executes all N Cases in numeric filename or collection array order,
for N * X independent executions per Issue. Case IDs must be unique among inputs.

```text
tmp/experiement1/agents/nanocoder/
  prompt-template.txt
  agent-scenario.txt
  cases/
    issue_1057/
      0001.json
    issue_1237/
      cases.json
```

Example `0001.json` (an input shape, not a recommended experimental test):

```json
{"case_id":"test-001","inputs":[{"input_id":"task","payload":"Your generated task"}]}
```

Multiple inputs form one Case/session. Each repetition executes all inputs in
order within that session; every Case execution starts a new session and workspace.
The shared experiment prompt and Agent scenario belong to
the upstream testing-agent workflow. Use fresh testing-agent sessions and keep
Issue reports, reference trajectories, existing results and GT out of their
context. The host maps submissions to Issue folders; every Issue for the same
Agent receives the same Agent-level scenario. The CLI imports whatever Cases
have already been supplied; it does not manage a live coding-agent session.

## Run

```powershell
python -m agentbench exp1 run nanocoder --case-dir tmp/experiement1/agents/nanocoder/cases

python -m agentbench exp1 run nanocoder --case-dir tmp/experiement1/agents/nanocoder/cases --tests 30 --workers 4 --prompt-template tmp/experiement1/agents/nanocoder/prompt-template.txt --scenario-file tmp/experiement1/agents/nanocoder/agent-scenario.txt
```

The round count is **per Issue**, defaults to 50, and accepts 1 through 50.
For example, `--tests 10` runs every supplied Case ten times with unchanged
inputs. One Case produces 10 executions; three Cases produce 30. Rounds and
Cases run sequentially within an Issue; `--workers`
limits concurrent Issues. Each Case execution gets a new native Suite, Agent session,
and workspace initialized from the configured empty state or fixture. A failure
is retained and the next repetition still runs. Automatic retries are disabled.
Each invocation creates a new experiment and is not a resume.

Each repetition uses `EvaluationService.execute`, preserving normal container
isolation, interception, cleanup and trajectory storage.
`--model` affects the target Agent. `--timeout` is forwarded to native execution.
When a reference declares `commit_version`, the service prepares an isolated
target at that exact commit. Different Issues may select different revisions in
one invocation; identical revisions reuse the prepared target. Git units reuse
their existing build recipe. Install units must declare a historical source-build
recipe (currently supplied for Nanocoder); package locks are never relabeled as
another commit. Unsupported preparation fails before Case execution. References
without a revision retain the configured default target. The experiment plan
records `prepared_targets` per Issue; the default registry/unit stays unchanged.

The oracle always uses the default **OpenRouter** configuration
(`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and its configured provider endpoint).
Target-provider selection, `ABB_MODEL`, and legacy `ABB_LOCAL_JUDGE_*` / `ABB_GT_*`
model overrides do not select this oracle. `ABB_GT_MAX_BYTES` bounds oracle
context size; oversized evidence remains inconclusive instead of being truncated.

GT is loaded from the registered Agent's
`ground_truth/issue_<number>/verify.case.json` and validated reference
`runs/*/trajectory/*/trajectory.json` files. This adapter does not change the
existing legacy `gt` command. Only generated Cases and the public Agent Profile
are passed to execution; hidden reference definitions stay on the host.

## Assess and read saved results

```powershell
python -m agentbench exp1 match --experiment <experiment-directory>
python -m agentbench exp1 result --experiment <experiment-directory>
```

`match` never executes the target Agent. It uses frozen reference snapshots and
saved Suite trajectories. It reuses completed, identical oracle requests.
Failed or interrupted requests stay pending; `match --retry-failed` explicitly
allows another oracle call, retains its previous journal entry, and consumes no
target-test budget. Concurrent matching of one experiment is locked out.

The oracle compares the reported failure with actual candidate actions and
outputs and the reference evidence. It must cite valid trajectory steps.
Merely describing/predicting a defect is not a hit. Different test inputs can
trigger the same defect, and subsequent recovery does not erase a trigger.
Missing/rejected evidence, incomplete negative evidence, and oracle failures
remain `null`, never automatic negatives. Execution failure alone is not a hit.

Each experiment retains `plan.json`, optional prompt text, the public profile,
per-Issue reference snapshots, per-repetition Suite locations, execution records, full oracle
requests/responses, assessment history, and `result.json`. Default output is
`<case-dir>/../results/exp1_<id>/`; `--results-dir` selects another parent.

Results include per-test decisions, per-Issue execution attempts, hit counts,
first-hit round indices and Detection@1/5/10/20/50. The denominator is the frozen set
of input Issue folders. Duplicate hits count once per Issue. Prefixes use round
order, not completion order. A cutoff larger than `--tests` is `outside_budget`.
For other cutoffs, pending decisions or insufficient tests leave the value null
unless a hit already establishes that Issue's success. Bounds retain all Issues
in the denominator. Rates are fractions in [0, 1].

Each `issue_<number>/repetitions/0001/execution.json` records that repetition's
round index, source Case index and ID, Suite path, state, execution status
(when available), and `wall_seconds`. Execution numbering follows round then Case order.
The issue's aggregate `execution.json` retains all repetition records; result
rows expose `round_index`, `case_id`, `suite`, `execution_status`, and
`execution_wall_seconds` separately. Round summaries aggregate times and detection:
a round is a hit if any Case hits, negative only if all Cases are negative, and
otherwise inconclusive. Detection@k covers the first k complete rounds.
The per-repetition timer includes preparation, target execution, and cleanup;
matching time is recorded separately. Failed repetitions also retain their time.
Existing experiments without an execution mode remain readable and
matchable with their original one-execution-per-Case semantics.

Execution and matching wall time are recorded separately. Available target-token
usage and oracle usage are retained; missing usage is not invented. Upstream
testing-agent token consumption is not observed by this Case-import interface.
Machine-readable JSON goes to stdout, progress to stderr. Exit zero means a
result was produced; inspect `status`, decisions and metric availability for
incomplete execution or assessment. `result` is read-only and needs no model
credentials. No live or paid evaluation is required to read saved results.

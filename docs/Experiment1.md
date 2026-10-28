# Experiment 1: behavioural failure detection

`agentbench exp1` executes one externally supplied Case group for independent rounds and measures
whether its executions trigger the reported failure of each ground-truth Issue of
the target Agent. It does not generate Cases, request a testing-agent diagnosis,
invoke a Judge, or open the viewer.

## Workflow

1. A testing agent generates a Case group from the shared experiment prompt and
   the Agent scenario.
2. `exp1 run` executes every Case in the group once per requested round.
3. Each saved trajectory is compared with every Issue of the Agent, and the
   command reports per-Issue hits and Detection@k.

## Input

A Case group is one directory. It contains either numbered JSON files, each
holding one native ABB Case, or a single `abb.cases.v1` collection named
`cases.json`. Do not mix these formats or add subfolders. Numbered files use
numeric order; collections use array order. Case IDs must be unique.

```text
tmp/experiement1/agents/nanocoder/
  prompt-template.txt
  agent-scenario.txt
  cases/
    run-01/
      0001.json
      0002.json
```

The Case group name (`run-01` above) is an opaque label chosen by the host. It is
not tied to any Issue.

Example `0001.json` (an input shape, not a recommended experimental test):

```json
{"case_id":"test-001","inputs":[{"input_id":"task","payload":"Your generated task"}]}
```

Multiple inputs form one Case/session. Each Case starts a new session and
workspace in every round; its inputs share that session. The shared experiment prompt and Agent scenario belong to
the upstream testing-agent workflow. Use fresh testing-agent sessions and keep
Issue reports, reference trajectories, existing results and GT out of their
context. The CLI imports whatever Cases have already been supplied; it does not
manage a live coding-agent session.

## Issues

Issues are discovered from the registered Agent's ground truth: every
`ground_truth/issue_<number>/` folder that contains `case.verified.json` takes
part, in numeric order. Folders without `case.verified.json` are skipped. Each
selected Issue must also provide a validated reference
`runs/*/trajectory/*/trajectory.json`; an Issue that fails validation stops the
command before any Case is executed. The legacy `gt` command is unchanged.

The configured Agent revision must equal each reference's `commit_version` when
declared; the command does not silently upgrade, downgrade or edit the target.
Only Cases and the public Agent Profile are passed to execution; hidden reference
definitions stay on the host.

## Run

```powershell
python -m agentbench exp1 run nanocoder --case-dir tmp/experiement1/agents/nanocoder/cases/run-01

python -m agentbench exp1 run nanocoder --case-dir tmp/experiement1/agents/nanocoder/cases/run-01 --tests 10 --workers 2 --prompt-template tmp/experiement1/agents/nanocoder/prompt-template.txt --scenario-file tmp/experiement1/agents/nanocoder/agent-scenario.txt
```

`--tests X` specifies the number of rounds, from 1 through 50 (default 50).
Every round executes all N supplied Cases in their saved order, producing N × X
independent executions. Each round gets a new Suite; each Case gets a fresh Agent
session and workspace through `EvaluationService.execute`. `--workers` limits
concurrent Cases within a round. A failed round is recorded, and later rounds
still run. Automatic target retries are disabled. The executions are shared by
all Issues, so execution cost does not grow with the number of Issues.
Each invocation creates a new experiment and is not a resume.

Existing preparation, container isolation, interception and trajectory storage
are reused. `--model` affects the target Agent. `--timeout` is forwarded to
native execution.

The oracle always uses the default **OpenRouter** configuration
(`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and its configured provider endpoint).
Target-provider selection, `ABB_MODEL`, and legacy `ABB_LOCAL_JUDGE_*` / `ABB_GT_*`
model overrides do not select this oracle. `ABB_GT_MAX_BYTES` bounds oracle
context size; oversized evidence remains inconclusive instead of being truncated.

## Assess and read saved results

```powershell
python -m agentbench exp1 match --experiment <experiment-directory>
python -m agentbench exp1 result --experiment <experiment-directory>
```

`match` never executes the target Agent. It uses frozen reference snapshots and
the saved Suite trajectories, comparing each Case execution with each Issue,
so it makes up to Cases × rounds × Issues oracle comparisons. It reuses
completed, identical
oracle requests. Failed or interrupted requests stay pending;
`match --retry-failed` explicitly allows another oracle call, retains its previous
journal entry, and consumes no target-test budget. Concurrent matching of one
experiment is locked out.

The oracle compares the reported failure with actual candidate actions and
outputs and the reference evidence. It must cite valid trajectory steps.
Merely describing/predicting a defect is not a hit. Different test inputs can
trigger the same defect, and subsequent recovery does not erase a trigger.
Missing/rejected evidence, incomplete negative evidence, and oracle failures
remain `null`, never automatic negatives. Execution failure alone is not a hit.

Each experiment retains `plan.json`, optional prompt text, the public profile,
per-Issue reference snapshots, a Suite and execution record for each round, full
oracle requests/responses, assessment history, and `result.json`. Default output
is `<case-dir>/../results/exp1_<id>/`; `--results-dir` selects another parent.

Results include one execution row per Case per round, with its Case ID, round
index, Suite, outcome, and execution duration when the attempt reached completion.
Each `execution/rounds/NNNN/execution.json` also records the round's total wall
time, state, and Suite. Failures before an attempt has timing retain the round
wall time and an error; the per-Case duration remains null.

Every saved execution is compared against each Issue. A round is a hit for an
Issue if any Case hits, negative if every Case is negative, and inconclusive
otherwise. Hit counts, first-hit indices, and Detection@1/5/10/20/50 use rounds.
The denominator is the set of discovered Issues. Prefixes use round order, not
completion order. A cutoff larger than `--tests` is `outside_budget`.
Pending decisions leave a metric unknown unless a hit already establishes that
Issue's success. Bounds retain all Issues in the denominator. Rates are in [0, 1].

Execution and matching wall time are recorded separately. Available target-token
usage and oracle usage are retained; missing usage is not invented. Upstream
testing-agent token consumption is not observed by this Case-import interface.
Machine-readable JSON goes to stdout, progress to stderr. Exit zero means a
result was produced; inspect `status`, decisions and metric availability for
incomplete execution or assessment. `result` is read-only and needs no model
credentials. No live or paid evaluation is required to read saved results.

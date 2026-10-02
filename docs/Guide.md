# ABB operation guide

English | [中文](otherLanguages/Guide.zh-CN.md)

ABB runs Agents, schedules Cases and saves execution evidence. KUMA defines the
evaluation contract and calls DefuzeX for Case generation and judging. OpenRouter
provides the tested Agent's model; tools such as Tavily use their own services.
Their credentials and quotas are separate.

## Prepare the host

Use a source checkout with an editable installation; the standalone wheel does
not include all Agent resources and built viewer assets. Install Git, Python 3.10+
with pip/venv, and Docker accessible to your user for Docker Agent execution.
The offline demo needs no Docker. Platform instructions are in
[detailed reference](README-previous.md#before-you-start).

The viewer build requires npm and Node.js 20.19+ on 20.x, or 22.12+, as specified
by the locked Vite dependency. Python serves the built viewer; installing Python
packages does not build it. Headless runs can skip Node and use `--no-view`.
Agent-specific databases, browsers and tool dependencies are separate requirements.

## Verify without credentials

From the checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
agentbench --help
agentbench sdk list
python -m examples.offline_demo --output results/offline-demo.json
```

The SDK list should contain `kuma` and `local`. The demo uses a local echo Agent and deterministic
Judge: expect `Case execution: 1/1 completed | Judge: pass=1`. This tests the local
flow, not the official service. Copy the timestamped path printed as `OFFLINE_RESULT`.

```bash
cd web
npm ci
npm run build
cd ..
# Replace this example with the actual OFFLINE_RESULT path.
agentbench view results/offline-demo-YYYYMMDD-HHMMSS.json
```

Open the complete printed `View:` URL, including its Suite path. Keep the viewer
running; Ctrl+C stops it. The address root opens Benchmark Overview and lists saved Suites in the sidebar;
`/suite/SUITE_ID/` selects one. The list refreshes automatically, including new runs
and reruns, and discovers canonical Suites under project `results/` plus registered
external Suite directories. Unavailable history is reported without hiding valid results.
Suite cards start collapsed and show execution completion and Judge counts. Use
each card's arrow to expand its Agents and Cases, or click the card to open that Suite.
Each Suite also shows its recorded evaluator (KUMA, Local, or another SDK) in the
sidebar and page header. The label comes from saved execution configuration;
unknown or mixed historical sources are shown explicitly. It does not identify
the Agent under test or the person who started the run.
CLI runs reuse a running project viewer and print a link to their own Suite on that
same address. When starting a viewer, port 8765 is the default; ABB selects an
available port when it is occupied. Rebuild after frontend changes. Normal use
does not require `npm run dev`.

Opening a Case selects **Judge** first, with its verdict, findings and recorded
reasoning. Report metadata and the complete JSON remain available below the results.
Selecting an older Attempt shows only that Attempt's report. **Timing** contains
the main sequence, waterfall and topology views; expand **Trace details** there for
OTel and execution flow. Existing `tab=trace` links open Timing, while explicit
Overview links retain their destination.

Benchmark Overview starts with SDK tabs (for example **KUMA** and **Local**). Each tab
shows only that SDK's Agents, Suites, Cases and reviewed discoveries. The selected
tab is retained in `?sdk=...`; **Export JSON** exports that tab's data. Missing,
partial and mixed evaluator records appear in separate tabs without crediting
their results to a named SDK. The sidebar continues to list all saved Suites.

Benchmark Overview measures discovery of known Agent defects against human-confirmed
ground truth. Each Agent can keep its reference defects and observations in
`ground_truth/` beside `agent.toml`. An explicit assessment records whether a Case
reproduced a defect and whether its Judge identified it. Discovery counts unique
defects, so reproducing the same defect repeatedly does not inflate the total.
Agents without ground truth show **Not configured**; those without assessments show
**Not assessed**. Neither is shown as a zero discovery rate. See the
[ground truth contract](Ground%20Truth.md) for storage formats and assessment inputs.
The visible percentage is **observed GT coverage** over that SDK's saved history.
The separate **Benchmark score** remains **Protocol not configured** until a
shared Agent/GT set, fixed budgets and independent trials can be enforced. The
[proposed scoring protocol](Benchmark%20Scoring.md) defines GT Discovery@B and
separate Case, Judge and reliability metrics; historical coverage is not a ranking.

Suite and Case totals remain available per Agent. For example, two Suites with ten
Cases each show `2 Suites × 10 Cases` and a total of twenty. Expand an Agent for
ground truth outcomes and its Suite breakdown. Different Suite sizes are summed
individually. New runs and reuse admissions update these totals live.

Total Cases includes planned and queued slots. Reuse adds new Case slots, even
when the saved Case ID is identical; retries of one slot do not increase the total.
Execution completion in the Suite breakdown does not mean ground truth discovery
or a passing Judge verdict. A Judge's `issue` alone is not a ground truth match.
Missing, corrupt or ambiguous Suites are excluded with a warning. No Agent code
or evaluation is run to collect these statistics. Export the current totals and
per-Agent Suite breakdown as JSON, or read `GET /api/benchmark/overview` locally.
That API retains all-SDK aggregates and adds independent groups in `evaluators`.

## Configure services

Preserve an existing environment file:

```bash
test -f .env || cp .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
ABB_MAX_PARALLEL_CASES=1
```

See [credential links and the command/service matrix](README-previous.md#configure-a-real-evaluation).
Nonempty `KUMA_API_KEY` takes precedence over ABB's `DEFUZEX_API_KEY` alias.
`OPENROUTER_MODEL` is a required model slug, not a key; the example is not a runtime
fallback. Tavily is required only by Agents using its search tool.

Exported shell variables override `.env`, including exported empty values.
`--env-file PATH` selects another file; `--model MODEL` overrides the Agent model.
The runtime forwards declared configuration rather than mounting the whole `.env`.
The bundled ReAct model route does not require a real host `ANTHROPIC_API_KEY`.

For host KUMA validation or assisted Agent configuration:

```bash
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
python -c "from importlib.metadata import version; import kuma; print(version('kuma-defuzex')); print(kuma.__file__)"
```

The distribution is `kuma-defuzex`, the import is `kuma`. Host and container packages
are separate; select this venv in your IDE. Do not use the obsolete `.[defuzex]` extra.

## Run a Case, then a Suite

```bash
docker info
agentbench observe --list
agentbench evaluate react-agent --cases 1 --no-view
agentbench run
# Non-interactive and headless:
agentbench run --yes --no-view --results-dir results
```

A Case can contain multiple ordered inputs. `run` selects enabled ready Agents and
uses their registry `case` counts. Readiness certifies integration, not a guaranteed
Judge pass. Check [the registry](../resources/registry.toml) for current selection.

`ABB_MAX_PARALLEL_CASES=4` permits up to four Cases across the Suite, including
Cases of the same Agent. It does not limit tool concurrency inside an Agent.

Official KUMA Judge submission runs on the host after Docker cleanup, with a
separate FIFO queue. `ABB_MAX_PARALLEL_JUDGES` defaults to `2` and
`ABB_JUDGE_QUEUE_CAPACITY` to `8`. Saved tasks resume without executing the Agent
again. See [Host Judge queue](Host%20Judge%20Queue.md) for limits and recovery.

Agent traffic that is neither a declared model route nor a tool route goes to the
[egress observer](../agentbench/services/egress-observer/README.md). It admits the common
package registries (PyPI, npm, Debian/Ubuntu, Maven Central, crates.io, Go proxy), so a
tool's `pip install` works, and refuses everything else. Every attempt is written to
`egress.jsonl`, next to the model traffic in `network.jsonl`. A refusal is recorded as
Agent behavior and does not reject the Case. `ABB_EGRESS_ALLOW=host[:port],...` adds
destinations; `ABB_EGRESS=open` forwards every destination (still recorded in
`egress.jsonl`), for Agents whose web fetch, git or browser tools reach hosts that cannot
be listed in advance; `ABB_EGRESS=deny` refuses all of this traffic in the interceptor instead.

## Smoke-test an Agent without KUMA credit

`--sdk local` runs the same container, model interception and host trace checks as
`kuma`, with fixed generic Cases and a local Judge instead of the KUMA Backend. It needs
no `KUMA_API_KEY` and spends no KUMA credit; the Agent's own model calls still cost what
they cost. Use it to prove an Agent runs from Case to Judge before a paid evaluation.
Its verdict is not a KUMA behavior judgment.

```bash
agentbench evaluate react-agent --sdk local --cases 1 --no-view
```

- Each Case asks up to three generic questions about the Agent itself. The registry
  `step` limit still applies.
- The Judge reports `issue` for a failed step and `insufficient_evidence` for a step
  without SDK trace evidence. Otherwise one lenient model call checks that the answers
  are coherent. The host makes that call, not the container, so the key never reaches
  the Agent and the call is never recorded as Agent evidence.
- The Judge uses the Agent's model target (`OPENROUTER_BASE_URL`, `OPENROUTER_MODEL`,
  `OPENROUTER_API_KEY`). `ABB_LOCAL_JUDGE_BASE_URL`, `ABB_LOCAL_JUDGE_MODEL` and
  `ABB_LOCAL_JUDGE_API_KEY` select another OpenAI-compatible chat completions endpoint;
  set them when the Agent's target serves Anthropic messages.
- Commands without `--sdk` keep using `kuma`; `local` is selected only by name.
- The run directory also keeps `local-judge.json` with the Judge model, its verdict and
  the raw reply.

## Add an Agent

Follow [How To Add Agent](How%20To%20Add%20Agent.md): configure the environment,
run the add command, then review what each file does. It has the same six languages
as the README. Generated configuration and certified execution are separate stages.

## Interpret and share results

| State | Meaning |
| --- | --- |
| Completed + `pass` | Met the Case criteria. |
| Completed + `issue` | Judge found a behavioral problem; inspect the cited evidence. |
| Completed + `insufficient_evidence` | Required behavior was not established; not a proven defect by itself. |
| Blocked / host rejected | Execution or evidence acceptance failed; a report may still be retained. |

Inspect both execution and Judge status instead of reading aggregate `FAILED` as
container failure. For partial OTel, inspect the reason: attribute filtering,
missing spans and export failure are different conditions.

Managed Suites retain plans, Cases and `events.json` under `results/suites/<suite-id>/`.
`run`, `evaluate` and `certify` accept `--results-dir DIR` to select the ABB result
directory explicitly. Missing directories are created; dotted names are directories
too. For example:

```bash
agentbench evaluate react-agent --cases 1 --yes --no-view --results-dir results/my-run
```

The canonical event log is `results/my-run/suites/<suite-id>/events.json`, alongside
the Suite plan and saved Cases. Use the exact `Result saved` path with `agentbench view`;
the directory remains the source for resume/retry and later host Judge updates.
Legacy `evaluate --result-output PATH` and `run`/`certify --output PATH` remain
compatible, but a file path only selects its parent for managed Suites: the requested
filename is not created. They print a migration notice; use `--results-dir` instead.
`evaluate --output DIR` independently selects the SDK artifact directory. Selecting
an ABB result directory does not relocate SDK traces. The live viewer uses the saved
Suite references to reach those artifacts.

Detailed attempts live under `results/observe/<run-id>/`; Judge reports are normally
at `evaluation/judge/report.json`. Use the printed paths and exact attempt IDs.

`resume SUITE` continues eligible unfinished work. `retry SUITE --agent ID --case N`
targets one unfinished Case (N starts at 1). `reuse SUITE` submits saved Cases to a
linked reuse Suite. An uncertain accepted request or unsafe replay can remain blocked.
Changing a Profile does not change saved Cases; generate new ones to test the new Profile.

To rerun one saved Case through fresh Agent execution and judging, use its Case ID
or artifact run ID from the viewer/results directory:

```bash
agentbench reuse CASE_ID
agentbench reuse ARTIFACT_RUN_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 2
```

`--case` starts at 1. A saved `case.json` path or an attempt directory/file path is
also accepted. IDs search project results and indexed external Suites;
`--suite-root DIR` limits lookup to another results directory. If an ID occurs in
multiple Suites (including earlier reruns), the command prints explicit source
commands to choose from. A Suite ID without `--agent`/`--case` still reuses all Cases.
Standalone traces without a canonical Suite plan cannot be reused.

CLI and Viewer requests join a running reuse Suite in the same project when their
SDK/model settings, credentials and Agent provenance match. An explicit `--output-root`
also restricts which destination can be joined. Otherwise, a new Suite is created.
Every intentional request adds fresh Case slots, including repeated requests for the
same Case ID. Each slot copies the exact saved artifact, records its source Suite/Agent/
Case position, and creates fresh execution evidence and a new Judge result. It does
not run Case generation. Current Agent code is used with the saved runner settings;
`--model` and `--max-steps` can override those settings. Original results are retained.
This schedules one new evaluation, subject to the configured recovery policy; it
does not resubmit the previous evidence to Judge.

Newly admitted Cases appear as queued work while the current scheduler pass finishes;
the next pass executes them under the saved concurrency limits. Once the batch has
drained and completed, the next reuse starts a new Suite. Requests from different
processes share the same admission lock, and repeated delivery of one request ID
does not add another execution. The original plan remains unchanged; additional
slots and their provenance are recorded in the ordered event log.

In a local `agentbench view` session, open a Case and click **Rerun this Case**.
**Open reuse Suite** switches to the batch's progress/results on the same viewer and port.
The original and reuse Suites both appear in the sidebar. Once the Case
artifact is saved, reuse reads an atomic
snapshot and can execute independently while the original Suite continues. Ordinary
progress updates do not invalidate a reuse request. The copied Case records the
source event revision and verifies the original artifact digest.
Keep the process that owns the batch running; stopping it cancels that batch.
Interrupting a CLI command that joined another process's batch only stops its wait.
Accepted requests and copied inputs remain available, including requests queued
before an interruption. The printed/saved `events.json` remains available for
`agentbench view` and `agentbench resume`. Rechecking an uncertain request keeps the
same command identity and destination, so transport retries do not create extra runs.

The viewer exports a JSON snapshot, not all traces or a standalone HTML report.
Preserve Suite and referenced attempt directories for full evidence; moving to a
new machine can require path adjustments. `web/dist/index.html` depends on assets
and local APIs and cannot be shared alone as the report.

Use `agentbench clean --dry-run` before history cleanup. Confirmed cleanup archives
unreferenced history into `cache/history-trash/`, preserving saved Suites and their
referenced artifacts. Stop runs/viewers first. It does not remove Agent source,
credentials, registry state or Docker images.

See [troubleshooting](Troubleshooting.md) and
[the documentation issue audit](Documentation-Issue-Audit.md) for further details.

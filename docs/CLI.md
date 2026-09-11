# AgentBench CLI

## Container evaluation and Case-local conversations

The default `run`, `certify` and `evaluate` select the built-in `kuma` evaluation
plugin, which invokes the same container-local KUMA/Agent/OTel core. All three
commands accept `--sdk` and `--sdk-options` through the same SDK selection factory.
`evaluate` runs the selected Agent for its Registry `case` count, or `--cases N`.
`observe` remains SDK-free. A plain `create_run()` SDK uses the host-side adapter;
an `EvaluationSDKPlugin` can supply another formal runner.

`run` still selects enabled ready Agents and executes Registry `case` counts.
`certify` runs the adapting Agent's requested Cases and promotes only after
host-side artifact identity/completion checks pass. A Judge `issue` is a benchmark
failure for `run`, but does not prevent certification of an executable Agent.
Each Case gets a fresh container and one Agent adapter for all its Inputs.
Case-local context delivery is declared in `evaluation/input-contract.json`.
Raw artifacts are saved even without the suite `--output` option.

`python -m agentbench evaluate 02 --cases 2 --max-steps 4` runs two independent
Cases, each with up to four SDK Inputs. Omitting the selection opens a prompt once.
SDK Inputs remain unchanged in the ledger; the configured context policy prepares
the actual Agent input separately and records it in `mapped-input.json`. This command
can incur official Case/Judge and model charges. It does not promote Registry status.

For this default KUMA adapter, the Agent needs evaluation/profile.md and
evaluation/input-contract.json. KUMA_API_KEY or legacy DEFUZEX_API_KEY is required.
SDK state is mounted writable under the actual Agent repository's .kuma only.
The temporary evaluation build enables only official KUMA GET/POST egress in
addition to the Agent's existing routes; original manifests are not changed.

Exit 0 means execution and OTel completed and a Judge report was received, not
necessarily a passing verdict. Failures exit 1, argument errors 2, interruption
130. Artifacts remain under the printed run directory, with SDK files in
evaluation/ and SDK recovery state in sdk-repo/.kuma/. The actual staged Agent
source is mounted read-only at /opt/agent/agent; its nested .kuma mount is writable
on the same filesystem, as required by SDK ledger validation.
No automatic paid rerun occurs.

### `evaluate` options

| Argument | Default | Meaning |
| --- | --- | --- |
| `selection` | Prompt once | Enabled Agent number or ID. |
| `--cases N` | Registry `case` | Positive number of independent Case executions; no ABB upper cap. |
| `--max-steps N` | SDK default | Positive upper bound on Inputs per Case, subject to SDK limits. |
| `--registry PATH` | Bundled registry | Agent registry to read. |
| `--env-file PATH` | Project environment search | Load environment settings. |
| `--model NAME` | Environment configuration | Model used for intercepted Agent calls. |
| `--sdk NAME` | Built-in `kuma` | Installed plugin name or `python:MODULE[:OBJECT]`. |
| `--sdk-options PATH` | Empty options | JSON object passed to the selected SDK. |
| `--sdk-source PATH` | Selected SDK's default | Explicit override for its `sdk_source` option. KUMA defaults to the sibling `Defuze-SDK` checkout. |
| `--result-output PATH` | `results/evaluate-<agent_id>.json` naming base | ABB-owned suite result JSON, independent of private SDK files. |
| `--output PATH` | Selected SDK's default | Explicit override for its `output` option. KUMA defaults to `results/observe`. |
| `--timeout SECONDS` | Selected SDK's default | Positive finite override for its `timeout` option. KUMA defaults to 2400 seconds. |

`--sdk-source`, `--output`, `--timeout`, and `--max-steps` are explicit SDK option aliases. They override
matching keys in `--sdk-options` only when explicitly supplied. Other SDKs receive
none of KUMA's defaults and must support any aliases the caller explicitly passes.
For another SDK, Input count, credentials, deployment and artifact support follow
that SDK's contract. A completed `evaluate` needs a report; `issue` still exits 0.

```bash
python -m agentbench evaluate my-agent --sdk python:my_package:configured_sdk \
  --sdk-options evaluation.json
```

Open a saved observe/evaluation run without Node.js using
`python -m agentbench view results/observe/<run_id>/run.json`.
The OTel tab offers a React Flow execution graph and a call tree. It checks JSON
every second (serial requests, no overlap), with a pause control for the OTel view.
The run list, SDK panel and current raw-event page also poll automatically.
Graph arrows mean parent/child calls, not inferred dataflow or static LangGraph
topology. New executions publish active span snapshots in `otel-live.jsonl`;
completed spans in `otel.jsonl` supersede snapshots by trace/span ID. Existing
images must be rebuilt to produce live snapshots; historical ended spans still
display. Polling does not create Agent, model or SDK requests.

Its local read-only API lists sibling runs under the selected run's parent
directory, newest first, and initially selects the requested run. Refresh updates
the list. Each run exposes OTel, SDK artifacts and paged raw events; paths cannot
escape the selected artifact root. Vite/preview lists its configured observe root.

This document is the complete usage guide for the AgentBench command-line
interface. The CLI installation entry point is defined in `pyproject.toml`, and
the implementation lives in `agentbench/cli/`.

## 1. Prerequisites

Run commands from the repository root:

```powershell
cd <path-to>\defuzeX_AgentBench
```

AgentBench supports two equivalent invocation forms:

```powershell
python -m agentbench <command> [arguments]
agentbench <command> [arguments]
```

The second form requires this project to be installed in the active Python
environment. Before running a benchmark, make sure that:

- Python 3.10 or later is available.
- The selected evaluator's requirements are met; built-in KUMA needs
  `KUMA_API_KEY` or the legacy `DEFUZEX_API_KEY`. Offline SDKs may need neither.
- Docker Desktop is running when the target Agent uses the Docker runtime.
- `OPENROUTER_API_KEY` is configured for intercepted Docker Agents.
- A model is supplied with `--model` or `OPENROUTER_MODEL`.
- Other required environment variables declared by the target Agent's
  `agent.toml` are configured.
- The Agent is registered in `resources/registry.toml`, and its directory,
  `agent.toml`, and requirement file exist.

Show root help with:

```powershell
python -m agentbench --help
```

Current subcommands:

| Command | Purpose |
| --- | --- |
| `run` | Run all enabled Agents whose status is `ready`. |
| `view` | Open an existing JSON result in the local web viewer. |
| `certify` | Verify one `adapting` Agent can complete its requested Cases and promote it to `ready`. |
| `observe` | Select one enabled Agent, supply native input, and save execution traces without an evaluation SDK. |
| `evaluate` | Evaluate one enabled Agent on independent Cases with the selected SDK. |
| `sdk` | List or inspect evaluation SDK plugins. |
| `clean` | Clear default local result history into a recoverable archive. |

### Clean local history

```bash
python -m agentbench clean --dry-run  # Preview only
python -m agentbench clean            # Preview and confirm
python -m agentbench clean --yes      # Skip confirmation
```

Stop active runs and viewers first. `clean` moves all immediate children of the
installed project's `results/` into a unique `cache/history-trash/` batch. This includes
observe/evaluation traces, certification/suite JSON, interception artifacts, and
SDK recovery state inside result directories. The results directory remains.
It does not change Agent sources, `.env`, registry certification status, Docker
images, SDK server records, or results written to custom paths outside `results/`.
Symlinked result roots are rejected; child symlinks are moved, not followed.

Cleanup is recoverable and does not free disk space. The command prints the archive
path. To restore, stop runs/viewers and move its contents back into `results/`,
without overwriting newer files. Restart viewers after cleanup; an existing viewer
bound to a removed run may need a new result path. `--dry-run` never moves files,
even with `--yes`. Cancellation exits 0, errors 1, interruption 130.

## 2. Default Command and Compatibility

`run` is the default command. These commands are equivalent:

```powershell
python -m agentbench
python -m agentbench run
```

The old no-subcommand argument form remains supported:

```powershell
python -m agentbench --output results\result.json
```

It is equivalent to:

```powershell
python -m agentbench run --output results\result.json
```

Root-level `-h` or `--help` shows all subcommands and is not rewritten to
`run --help`.

## 3. `run`

### 3.1 Syntax

```text
agentbench run [-h] [--registry PATH] [--env-file PATH] [--output PATH] [--no-view]
               [--model OPENROUTER_MODEL]
               [--llm-trace {off,terminal}]
               [--llm-trace-max-bytes BYTES]
```

```powershell
python -m agentbench run
python -m agentbench run --model openai/gpt-4.1-mini
python -m agentbench run --output results\result.json
python -m agentbench run --llm-trace terminal
```

### 3.2 Arguments

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `-h`, `--help` | No | - | Show `run` help and exit. |
| `--registry PATH` | No | Bundled Registry | Read this registry; `certify` updates this same file. Agent paths resolve from its parent directory's parent. |
| `--env-file PATH` | No | Repository `.env` | Load host-only secrets and defaults from another dotenv file. |
| `--output PATH` | No | `results/result.json` | Naming base for the unique, atomically updated suite JSON. |
| `--no-view` | No | Viewer enabled | Save results and run without starting a web server or waiting at the viewer prompt. |
| `--model OPENROUTER_MODEL` | No | `OPENROUTER_MODEL` | Force every intercepted Agent request to use this OpenRouter model slug. |
| `--llm-trace {off,terminal}` | No | `off` | Print sanitized model requests and responses captured by the transparent Interceptor. |
| `--llm-trace-max-bytes BYTES` | No | `262144` | Legacy name: streaming memory spool threshold, not a content limit. Payloads are retained completely. |

`PATH` is the naming base for the result file, not the final file name.
AgentBench adds a timestamp and always writes `.json`:

```text
--output results\result.json
-> results\result-20260820-162500.json
```

If a file name collides within the same second, AgentBench appends `-2`, `-3`,
and so on. Each run gets a new file. Within that run, every event updates a JSON
array by writing a temporary file and atomically replacing the previous snapshot.
If an update fails before replacement, the previous complete snapshot remains.

When `--output` is omitted, CLI `run` saves a unique `results/result-<timestamp>.json`
and starts its viewer before evaluation. The default container adapter separately
saves raw Case, OTel, submission and Judge artifacts under `results/observe`.
Use `--no-view` for unattended execution. The compatible Python `run()` / `main()`
API retains `output_path=None`; pass an output path to opt into its result viewer.

### 3.3 Agent Selection Rules

Default runs select only registrations that satisfy both conditions:

```toml
enabled = true
status = "ready"
```

Enabled Agents that are still `adapting` are excluded from normal batches. The
CLI displays the number of excluded Agents and suggests using
`agentbench certify <agent_id>`.

Registry order determines execution order. Each Agent's `case` field determines
how many independent Cases are run.

### 3.4 Confirmation Prompt

After displaying the selected Agents, the CLI asks:

```text
Continue? [yes/no]:
```

Accepted inputs:

| Result | Inputs |
| --- | --- |
| Continue | `yes`, `y`, `confirm`, `c` |
| Cancel | `no`, `n`, `cancel`, or an empty response |

Cancellation is not a benchmark failure and exits with code `0`.

### 3.5 Result Viewer Lifecycle

CLI `run` starts the viewer before the benchmark by default.
The terminal prints the suite URL, and after each Agent completes it also prints
a direct link with `#agent=<agent_id>`.

The Python process serves the built `web/dist` assets and read-only APIs in a
background HTTP thread. React executes in the browser; normal `run` does not
start Vite or need an `npm run dev` process. If frontend source changes, rebuild
once with `npm run build` from `web/` (install dependencies first if necessary).

Open the printed URL during execution. Suite progress, the run list, OTel and
Case/Judge views poll every second without reloading the page. The KUMA adapter
registers its artifact directory through a generic progress event before image
preparation, so details are available while the Case is running, not only after
its final validation. Data appears as it is written; pending files show as pending.
The suite viewer lists only registered runs associated with its selected Agents.
Custom SDKs always get suite progress; detailed tabs require ABB-compatible
artifacts registered through `BenchmarkProgress.artifact_directory`.
Completed-step callbacks still represent accepted results, not live timing.

The **Interactions** tab groups network requests, streaming chunks and responses
by `call_id`, and framework tool executions by `span_id`. Ant Design controls
provide type/Input/status/time filters, full-payload search, page sizes and page
jumps. New records show an update notice without moving the current page.
Details show parsed chat/tool messages, JSON, Case/Input value matches, callbacks
and independently paginated original records.
Append `#view=raw` to a viewer URL to open this tab directly.

After the run finishes, the CLI keeps the viewer alive and asks:

```text
Viewer action? [r rerun/q quit]:
```

| Action | Inputs | Behavior |
| --- | --- | --- |
| Rerun | `r`, `rerun`, `retry`, `again` | Stop the current viewer, create a new suite and result file, and run again. |
| Quit | `q`, `quit`, `exit`, or an empty response | Stop the viewer and return the benchmark exit code. |

`Ctrl+C` or end-of-input also stops the viewer.
During execution, Ctrl+C records an interruption, closes the viewer and exits 130.
Unexpected execution errors also close the viewer. A port binding failure is
reported without preventing evaluation or result saving. With `--no-view`, the
command returns immediately after evaluation without the viewer action prompt.

## 4. `certify`

### 4.1 Syntax

```text
agentbench certify [-h] [--env-file PATH] [--output PATH]
                   [--model OPENROUTER_MODEL]
                   [--llm-trace {off,terminal}]
                   [--llm-trace-max-bytes BYTES] agent_id
```

Most common invocation:

```powershell
python -m agentbench certify swe-agent
```

### 4.2 Arguments

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `agent_id` | Yes | - | Stable Agent ID from `resources/registry.toml`. |
| `--registry PATH` | No | Bundled Registry | Read this registry; `certify` updates this same file. Agent paths resolve from its parent directory's parent. |
| `--env-file PATH` | No | Repository `.env` | Load host-only secrets and defaults from another dotenv file. |
| `--output PATH` | No | `results\certify-<agent_id>.json` | Custom naming base for the certification result. |
| `--model OPENROUTER_MODEL` | No | `OPENROUTER_MODEL` | Force intercepted calls to use this OpenRouter model slug. |
| `--llm-trace {off,terminal}` | No | `off` | Print sanitized intercepted model traffic during certification. |
| `--llm-trace-max-bytes BYTES` | No | `262144` | Legacy name: streaming memory spool threshold, not a content limit. Payloads are retained completely. |
| `-h`, `--help` | No | - | Show `certify` help and exit. |

Unlike normal `run`, `certify` always saves a unique JSON result whether or not
`--output` is passed. Default example:

```text
results\certify-swe-agent-20260820-162500.json
```

Custom naming base:

```powershell
python -m agentbench certify swe-agent `
  --output results\manual-swe-certification.json
```

### 4.3 Allowed Registry States

`certify` operates on one specified Agent only and does not run other Agents.

| Current state | Behavior |
| --- | --- |
| `adapting` | Run full certification; change to `ready` when all requested Cases complete without startup, runtime, or invocation errors. Judge failures do not block promotion. |
| `ready` | Treat as already certified, return success, and do not rerun. |
| `planned`, `blocked`, or any other state | Refuse certification and exit with code `2`. |
| `enabled = false` | Refuse certification and exit with code `2`. |
| Not registered | Refuse certification and exit with code `2`. |

### 4.4 Full Certification Flow

Certification uses the same trusted host flow as normal benchmarks:

1. Load and validate the Registry, Agent directory, manifest, and requirement.
2. Check the selected evaluation SDK configuration.
3. Start the target Agent, including Docker build/runtime when applicable.
4. Generate a Case using the selected SDK.
5. Run each SDK Input.
6. Submit to the selected SDK's Judge.
7. Append complete events and results to the certification JSON.
8. Atomically update the Registry status from `adapting` to `ready` only when
   all requested Cases complete without startup, runtime, or invocation errors.

None of the following situations promote the Agent:

- Agent startup, runtime, or invocation failure;
- any requested Case does not complete;
- execution is interrupted;
- the Registry status changes during certification;
- the target Registry block is missing `status`.

A DefuzeX Judge failure means the Agent completed the workflow but did not
satisfy the benchmark. Certification still promotes the Agent because `ready`
means the adapter/runtime is runnable, not that benchmark quality is high.

The status update modifies only the target Agent's `status` line and preserves
field order, comments, and other Agents in the Registry. The temporary file is
created beside the Registry and is atomically replaced when complete.

### 4.5 Why Certification Does Not Keep a Viewer Running

`certify` is designed to be callable by developers and CI in non-interactive
contexts. It does not wait for `q` or `r` after completion, and it does not
start a viewer that would disappear when the process exits. The terminal prints
the result path and a command for opening it later.

View a certification result after it finishes:

```powershell
python -m agentbench view `
  results\certify-swe-agent-20260820-162500.json
```

## 5. `view`

The old static result dashboard has been removed. `view` now serves the minimal
Vite + React Trace page from `web/dist` and loads the bound run's raw events.
Build it first with `cd web && npm install && npm run build`. If the build is
missing, the page returns HTTP 503 with build instructions. The page supports
local JSON/JSONL imports, source filtering and expandable raw JSON; it does not
provide the old suite/Agent metric dashboard. Reload to fetch an updated snapshot.

### 5.1 Syntax

```text
agentbench view [-h] [--host HOST] [--port PORT] result_log
```

```powershell
python -m agentbench view results\result-20260820-162500.json
```

### 5.2 Arguments

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `result_log` | Yes | - | AgentBench `.json` result file to read. |
| `--host HOST` | No | `127.0.0.1` | Viewer HTTP server bind address. |
| `--port PORT` | No | `8765` | Preferred bind port. |
| `-h`, `--help` | No | - | Show `view` help and exit. |

Examples:

```powershell
python -m agentbench view results\result.json --port 9000
python -m agentbench view results\result.json --host 127.0.0.1 --port 0
```

If the requested port is already in use, the viewer automatically chooses an
available port. `--port 0` asks the operating system to choose the port
directly. When bound to `127.0.0.1`, the viewer is local-only and does not
require Node.js.

The terminal prints the real URL and absolute result path:

```text
View: http://127.0.0.1:8765/suite/suite_xxx/
Result log: <absolute-path>\result-20260820-162500.json
```

Press `Ctrl+C` to stop the server. A missing result path raises an error
immediately and does not create an empty file.

## 6. JSON Results and Interruption Recovery

Result files are JSON arrays of events and may contain:

```json
[
  {"event": "run_started", "suite_id": "suite_example", "selected_agent_ids": []},
  {"event": "suite_completed", "suite_id": "suite_example", "summary": {"selected": 0}}
]
```

This is ABB's storage format, independent of an Agent's communication protocol.
New suite events include source `abb` and a UTC timestamp.
The writer currently updates the whole document per event. Large, long-running
observation sessions will need the planned trace storage service.

| Event | Meaning |
| --- | --- |
| `run_started` | Suite ID and selected Agents. |
| `progress` | SDK lifecycle stage/status and optional host artifact directory for live inspection. |
| `step_started` | One SDK Input started, including input ID and payload. |
| `step_completed` | Input invocation succeeded, including standard output and trace-like raw state. |
| `step_failed` | Input invocation failed, including error type, message, and any captured output. |
| `agent_completed` | One Agent's Cases, report, and error summary. |
| `suite_completed` | Suite summary for passed, failed, skipped, and selected Agents. |
| `suite_failed` | Shared configuration failed, execution was interrupted, or an unexpected error escaped the runner. |

If the process is interrupted, the file may not contain `suite_completed`. The
viewer marks it as `running_or_interrupted`, but already appended Cases, steps,
and errors remain viewable.

Results may contain inputs, outputs, raw adapter state, and error messages.
Review result files for sensitive data before sharing or submitting them.

## 7. Exit Codes

| Exit code | Commands | Meaning |
| --- | --- | --- |
| `0` | `run` | User cancelled, or all selected benchmarks passed. |
| `0` | `certify` | Certification completed and promoted the Agent, completed with Judge failures but still promoted, or the Agent was already `ready`. |
| `0` | `view` | Viewer stopped normally. |
| `1` | `run` | No runnable ready Agents, shared configuration failed, or at least one benchmark failed. |
| `1` | `certify` | Certification did not complete because of shared configuration, startup, runtime, or invocation failure. |
| `2` | `certify` | Agent does not exist, is disabled, has a disallowed state, or Registry update failed after certification completed. |
| `2` | all commands | `argparse` detected an unknown command, unknown argument, or missing required argument. |
| `130` | `run` | Ctrl+C interrupted evaluation; written results are retained. |

Unhandled exceptions that are not converted by the CLI, such as a missing file
for `view`, usually exit Python with a non-zero status and print the exception.

## 8. FAQ

### Normal run did not display a viewer URL

Current CLI `run` saves a result and prints a URL by default:

```powershell
python -m agentbench run
```

Check that `--no-view` was not supplied and Agent selection was confirmed. If a
local port could not be bound, the terminal reports it and still saves results.
The Python compatibility API needs an explicit `output_path` to start a viewer.
`certify` saves its aggregate result without keeping an interactive web server alive.

### An `adapting` Agent does not appear in normal `run`

This is expected. Use:

```powershell
python -m agentbench certify <agent_id>
```

After certification completes without startup, runtime, or invocation errors,
the Registry automatically changes to `ready`, and the next normal `run` can
select the Agent.

### `certify` completed, but the Registry was not updated

Check the last terminal line. If the Registry status changed during
certification, or the target block is missing `status`, the CLI refuses to
overwrite it and returns `2`. Check `resources/registry.toml`, then certify
again.

### The viewer cannot open the default port

Use the URL printed by the terminal. If port `8765` is occupied, the CLI chooses
another port. If firewall or proxy behavior is unusual, explicitly use:

```powershell
python -m agentbench view <result.json> --host 127.0.0.1 --port 0
```

### Docker Agent fails during startup

Make sure Docker Desktop is running, then check the Agent's Dockerfile, worker
command, and `agent.toml`. AgentBench uses a read-only root filesystem and
mounts `/tmp` as a fresh writable tmpfs for each run. See
`How To Add Agent.md` for the full adaptation constraints.

## 9. CLI Development Structure

The CLI uses an explicit feature registry instead of hard-coding command
branches in the root entry point:

```text
agentbench/cli/
  main.py                 root parser and feature dispatch
  execution.py            shared benchmark execution and result writing
  presentation.py         terminal display and interaction
  registry_status.py      Registry status updates
  result_export.py        atomic JSON snapshot writer
  viewer.py               local HTTP viewer server
  features/
    base.py               CommandFeature contract
    __init__.py           FEATURES registry
    run.py                run arguments and workflow
    view.py               view arguments and workflow
    certify.py            certify arguments and workflow
```

When adding a subcommand:

1. Create a separate module in `agentbench/cli/features/`.
2. Implement `configure_parser(parser)` and `execute(args)`.
3. Export a `CommandFeature`.
4. Register it in `FEATURES` in `features/__init__.py`.
5. Put shared behavior in common CLI modules; do not duplicate benchmark or
   viewer lifecycle logic.
6. Add parser dispatch, success, failure, and boundary tests.
7. Update this document with the command, arguments, exit codes, and examples.

There must be exactly one `default=True` feature. The current default feature is
`run`.

## Observe (SDK-independent)

```sh
agentbench observe [ID_OR_NUMBER] [--list] [--input JSON_PATH]
                  [--registry PATH] [--env-file PATH] [--model MODEL]
                  [--output DIRECTORY] [--timeout SECONDS] [--show RUN_DIRECTORY]
```

Without an Agent argument, the menu shows all enabled Agents in Registry order, including `adapting`.
It asks for one number (or `q`), then native input fields declared by the Agent.
Without field declarations, enter a JSON value. Invalid interactive selections
can be retried. `--list` does not require Docker, credentials or an evaluation SDK.
`observe 1` selects Agent 1 directly, without redisplaying the menu or asking for its number.
The positional argument also accepts the stable Agent ID. `--agent ID_OR_NUMBER`
remains a compatibility alias, mutually exclusive with the positional argument.
Native input is still requested unless `--input` supplies it.
`--model` selects a model name, not an Agent; numeric values are rejected with a
hint to use `observe NUMBER`. Omit it to use `OPENROUTER_MODEL` from the environment.
Only the selected unit's files are validated.
Observe does not certify an Agent or change Registry status.

Defaults: registry `resources/registry.toml`, output `results/observe`, environment
repository `.env`, model `OPENROUTER_MODEL`, timeout from `runtime.timeout_sec`.
Timeout must be finite and positive and applies to execution, not image building.
Each run has a unique directory; the report, framework JSONL, network JSONL,
invocation input/result and diagnostics are stored separately.
`--show` reviews a saved run offline, displaying framework hierarchy and wire-call
correlation without starting a viewer server.

Current supported observe runtime: Docker `execution="oneshot"`.
One invocation starts a new container, not a multi-turn memory session.
Success or `q`: exit 0; configuration, execution or degraded trace: exit 1;
argument parsing: exit 2; Ctrl+C/EOF: exit 130. Report presence is not a quality verdict.
Observed operation failures mark an otherwise returned report as `degraded`.

See [Observe guide](observe/README.md) for Company setup, environment, artifacts,
protocol limits and verification evidence.

## Evaluation SDK selection

`run`, `certify` and `evaluate` accept `--sdk NAME` and `--sdk-options PATH`. `NAME`
comes from the `defuzex_agentbench.evaluation_sdks` entry-point group declared
by an installed Python distribution. AgentBench does not download or install
code during selection.

```powershell
python -m pip install acme-evaluation-sdk==2.1.0
python -m agentbench sdk list
python -m agentbench sdk show acme
python -m agentbench run --sdk acme --sdk-options sdk-options.json
python -m agentbench certify my-agent --sdk acme
```

`sdk list` reads package metadata without importing third-party plugin code.
`sdk show` and an actual run load only the selected plugin. If two distributions
publish the same name, use `DISTRIBUTION::NAME`. For an explicit development
import, use `--sdk python:MODULE[:OBJECT]`. The old `MODULE[:OBJECT]` spelling
remains compatible.

`sdk-options.json` must contain a JSON object. Its fields are passed to the SDK;
`repo_path` is supplied by ABB per Agent. Credentials and validation belong to
the selected SDK. CLI callbacks and result output are shared across SDKs.

Omitting `--sdk`, or using `--sdk kuma`, selects the official container-local
KUMA plugin (`allow_local=False`).
For that default, `--sdk-options` accepts `sdk_source`, `output` (raw artifact
root), `timeout` (per preparation/Case container), `max_steps`, and `case_collection`
(an existing saved collection to execute without generation). Old SDK options such as `requirement_path` or `allow_local`
are rejected instead of silently selecting the old execution path.
A selected plain `create_run()` SDK executes through the generic host-side
adapter. A plugin implementing `EvaluationSDKPlugin` can provide a formal
container runner. See [SDK.md](SDK.md).


### Host evidence and fresh-checkout viewer requirements

`evaluate` creates the ABB suite snapshot before SDK validation/execution, using
`--result-output` as a timestamped naming base. It retains progress, Inputs, Agent
outputs and the public SDK report even when the SDK writes no files. The default
base is relative to the selected Registry's project root. `--output` continues to
configure the SDK only. Failed/interrupted execution retains partial artifacts.
Execution failure or a missing Judge report exits 1; interruption exits 130;
a completed Judge `issue` exits 0 for `evaluate`.

Plain injected SDKs produce Host framework evidence at `results/observe/<run-id>`
under the working directory. Suite progress records the absolute directory, so
`agentbench view <suite-result.json>` finds Inputs, framework/OTel spans and public
Judge results. Host network/private SDK wire capture is explicitly unavailable.
Third-party execution plugins retain their own observation implementation and
return the common result contract.

The viewer requires prebuilt `web/dist` assets. In the repository's `web` folder,
run `npm ci` then `npm run build`. Missing index or referenced assets produce an
actionable error before opening a socket; automatic viewing failure never discards
the result. Existing assets need no Node runtime. `run --no-view` skips viewing.

### Case counts versus dialogue steps

`case = N` in the Registry is the default Case count. An explicit
`evaluate --cases N` overrides it. With the built-in KUMA adapter, ABB first
requests `generate_cases(count=N)`. If the backend explicitly rejects
batch generation with `case_batch_unsupported`, ABB makes N single-Case
generation calls in the preparation phase. It saves the original public batches
and an ordered `case-collection.json`, validates total size/content uniqueness,
then starts one fresh execution container per Case. Each execution imports its selected Case with
`create_run(case_batch=batch, case_index=i)` and never requests another Case.
A separate preparation container generates the batch without loading the Agent.
There are N Agent execution containers, plus that preparation container.

ABB rejects too few/many Cases, duplicate IDs, or normalized duplicate content
before any Agent step. No truncation or replacement draws are performed.
The single-Case fallback applies only to explicit batch rejection; timeouts,
quota failures and unrelated validation errors stop preparation. The SDK validates every Case's repository/strategy/batch binding and
opaque signature metadata. The content check ignores IDs and whitespace changes;
it is not a semantic paraphrase detector. Non-KUMA SDK plugins retain their
existing create_run contract unless their runner implements batch preparation.

A Case execution or Judge service failure stops the remaining executions for
that Agent and reports actual completed/requested counts. The already generated
Case collection remains in the preparation artifact directory. To reuse an already collected set without generation, pass an SDK options JSON
containing `{"case_collection":"/absolute/path/to/case-collection.json"}` via
`--sdk-options`. Its selected entry count must match the Registry/CLI count;
each imported Case is revalidated by the SDK. The original collection is retained.

`max_steps` limits inputs inside each Case, independently of Case count. When
omitted, KUMA chooses its default (currently a ceiling of ten). Explicit limits
are checked against service entitlements. The service may return fewer steps.

**Current deployed service limitation (2026-09-10):** a real `count=2` request to
`/sdk/v2/cases/generate/` returned HTTP 400 `invalid_request`, with detail
`Async Case generation currently requires count=1.` The SDK normalizes this specific rejection to `case_batch_unsupported`,
without exposing raw diagnostics. ABB records `mode=single_fallback` and
collects N individual results before execution. If any generation fails, partial
results are retained and no Agent execution starts. When native batching becomes
available, the first count=N request succeeds and the fallback is not used.
# Shared evaluation sessions

`run`, `certify`, and `evaluate` use the same trace-aware runner factory and
`run_benchmark_session` lifecycle. All three start the live viewer by default,
retain it after completion, and support `r` to run a fresh suite and `q` to close
the viewer. Use `--no-view` for noninteractive execution. Viewer startup failure
is reported and does not discard the result log.

`run` selects ready Agents; `evaluate` selects one enabled Agent for debugging;
`certify` checks an adapting Agent and updates registry status after the final
session result qualifies. `observe` remains Agent-only, without SDK CaseGen or
Judge. Existing certification and evaluate exit-code semantics are unchanged.

`evaluate` also supports `--llm-trace terminal` and `--llm-trace-max-bytes` through
the same trace factory as `run` and `certify`. Its existing `--output` remains an
SDK option; use `--result-output` for the BBA result file.

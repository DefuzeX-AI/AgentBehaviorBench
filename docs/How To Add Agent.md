# Add an Agent

English | [Français](otherLanguages/How%20To%20Add%20Agent.fr.md) | [日本語](otherLanguages/How%20To%20Add%20Agent.ja.md) | [中文](otherLanguages/How%20To%20Add%20Agent.zh-CN.md) | [한국어](otherLanguages/How%20To%20Add%20Agent.ko.md)

Use this runbook for a new Agent: **environment → source import → configuration →
static review → local smoke → KUMA → view → handoff or certification**. Run commands
from this ABB checkout's root, with its virtual environment active. Replace
`SOURCE`, `AGENT_ID`, `NN-name` and result paths with values printed by your run.

For a coding assistant, first read `AGENTS.md`, the onboarding issue and upstream
setup instructions. Record the requested scope, current checkout and `git status`;
preserve unrelated work. Never infer that a package can run just from its README.

**When to pause:** if the user requests step-by-step approval, report each stage's
command, outcome, evidence path and proposed next step, then wait for approval.
Otherwise continue authorized work without asking again at every checkpoint.
Before a new paid/external operation, confirm that authorization covers model
requests and sending source context, the profile and evaluation evidence to the
configured providers. Reuse authorization already given. Stop dependent work for
missing credentials, required user decisions, unsupported deployment or an
unresolved failure; keep completed artifacts. Never print keys or `.env` contents.
A checkpoint means inspect the evidence; it is not always a permission prompt.

## 1. Prepare the environment

### Install ABB and its host dependencies

Complete [ABB installation](README-previous.md#before-you-start) first. You need Git,
Python 3.10+ with an activated virtual environment, and a running Docker engine
for certification. Then install the selected SDK's host validation dependencies:

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
python -m agentbench --help
python -m agentbench sdk list
docker info
```

`sdk list` should show `kuma`; `docker info` must succeed as the same user who will
run ABB. Download/configuration generation alone does not require Docker, but
`-c` certification does. The host SDK installation and the SDK installed inside
an evaluation image are separate.

Verify the harness before configuring paid services:

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

Expected: `Case execution: 1/1 completed | Judge: pass=1`. Save the exact
`OFFLINE_RESULT=` path. This deterministic echo demo needs no Docker, key or model
call and does not test your Agent. If it fails, repair the host environment first.
Checkpoint: report the checkout path/revision, CLI/SDK discovery and demo outcome.
SDK discovery alone does not establish onboarding support (see section 2).

### Configure credentials and models

Create `.env` only if it does not already exist:

```bash
test -f .env || cp .env.example .env
```

Edit the file locally:

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key:** needed to fetch the current strategy catalog and to generate/judge
  Cases. ABB also accepts `DEFUZEX_API_KEY`; a nonempty `KUMA_API_KEY` takes precedence.
- **OpenRouter key and model:** used to generate integration files and run the
  Agent. The generation model must support **strict structured outputs**; a model
  that works for ordinary chat is not necessarily suitable. The sample model slug
  above is a configuration example, not an implicit runtime default.
- **Agent dependencies:** read its upstream setup instructions and prepare required
  tool keys, datasets and external services. A database driver does not start a
  database; downloading an Agent does not provision its whole deployment.

Key-retrieval links are in [the configuration guide](README-previous.md#configure-a-real-evaluation).
Exported shell variables override `.env`. Use `--env-file PATH` for another file.
The CLI resolves declared credentials; it does not mount the entire `.env` into
containers. Keep credentials out of source files and generated configuration.

### Prepare the viewer, if wanted

For the browser UI, install Node.js **20.19+ on 20.x, or 22.12+**, with npm, then:

```bash
cd web
npm ci
npm run build
cd ..
```

This prepares ABB's viewer, not an Agent's browser or Node/MCP dependencies.
Use `--no-view` on the add command below to skip starting the viewer; headless
execution does not require Node or `web/dist`.

## 2. Import source, then generate configuration

Start with source import only. This gives a review point before model calls:

```bash
python -m agentbench agent add https://github.com/owner/repository
```

`SOURCE` is the HTTPS repository URL itself, not a file or `/tree/branch` URL, or
an absolute local directory such as `/absolute/path/to/local-agent` or
`C:\work\local-agent` on PowerShell. No `-d` flag is needed. GitHub imports use the
default branch revision; there is no `--revision` option. Local imports omit `.git`
and record a SHA-256 content digest. Subsequent calls with the same canonical
source reuse the unit; they do not refresh it from an edited local directory.

**Checkpoint — imported:** record the actual unit path and `source-manifest.json`
revision. Read the original entrypoint, prompts, tools, input/state schema, UI
caller, Python constraints and lockfile. Identify external services and the exact
interface being deployed: a text graph is not its PDF upload UI. Import alone does
not register a runnable Agent. Do not skip `agent add` by copying a replacement
implementation directly into the registry.

Generate files using the same source after answering these deployment questions:

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view
```

`-b` plans, generates and validates integration files and registers `adapting`;
it does **not** build Docker. KUMA fetches a fresh strategy catalog before planning.
Read each group's purpose, availability, exact version and evidence requirements;
use the recorded snapshot rather than copying a strategy ID from another Agent.
If lookup fails, stop and fix credentials/connectivity; do not invent a selection.

If the planner asks for input, save factual answers in a local UTF-8 file and resume:

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view --answers answers.txt
```

Explain the real text-to-native mapping, session lifecycle, excluded UI features,
services and dependencies. Never invent business inputs. Read `build-result.json`
and the failed `steps/` entry before retrying; completed files are retained and
revalidated. Manual conflicts stop generation. Do not delete all progress or
repeat paid requests without changing the cause of failure.

**Checkout limitation:** this revision's `local` SDK supports evaluation, but has
no onboarding requirements/validation hooks. `add -b --sdk local` stops with
`Selected SDK has no onboarding requirements and validation`. Use KUMA generation
here, then local evaluation in section 5. If KUMA credentials are unavailable,
stop automatic generation; adding local onboarding support is a separate code
change. Do not assume a fix in another checkout exists in this one.

The combined shortcut below is only for a deployment you already understand and
are authorized to generate and certify without intermediate approval:

```bash
python -m agentbench agent add https://github.com/owner/repository -b -c --sdk kuma --no-view
```

`-c` builds/runs certification; it is a paid execution step, not a static check.
It can also run with manually prepared files. Currently automatic generation
supports LangGraph; do not relabel an unsupported framework as LangGraph.

| Option | Purpose |
| --- | --- |
| `--sdk kuma` / `--sdk local` | Choose explicitly; discovery does not prove onboarding support. |
| `--no-view` | Save results without launching the viewer. |
| `--build-model MODEL` | Model for configuration generation, requiring strict structured outputs. |
| `--model MODEL` | Agent model during certification. |
| `--answers answers.txt` | Answers to a previous plan. |
| `--with-observe` | With `-b`, generate native input prompts for `observe`. |
| `--build-settings settings.toml` | Overrides in a `[build]` table. |
| `-y` | Skip execution confirmation only when that execution is already authorized. |

Build-model precedence: `--build-model`, settings `model`, `OPENROUTER_BUILD_MODEL`,
then `OPENROUTER_MODEL`. Review the [packaged settings](../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)
before changing request budgets or retries.

## 3. Understand the files

The Agent unit is placed under `resources/agents/NN-name/`. The command generates
integration files around the imported source; you do not need to create all of
these by hand before running it.

```text
resources/agents/NN-name/
├── agent/                   # Imported upstream or local source snapshot
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — the Agent's own source

The imported source snapshot lives here. Its graph, reasoning and tools remain the
real implementation. Put ABB integration files outside this directory so that
adapting an Agent does not silently replace its behavior.

### `agent.toml` — how ABB starts and invokes the Agent

Defines the Agent ID, framework, source revision, Docker build/launch settings,
adapter, input/output mapping, environment declarations and model/tool routes.
Check that entrypoint paths and required inputs match the actual source. Declaring
a route or environment variable does not implement a tool or provision a service.

### `bindings/*.py` — how native inputs and outputs cross the boundary

Exports a synchronous, zero-argument factory returning the actual invokable Agent.
The binding handles source-backed input/output adaptation and lifecycle cleanup.
It must not fabricate answers or substitute a simplified Agent to pass a test.
Valid Python syntax alone does not prove the graph can load and execute.

### `Dockerfile` — what is installed inside the Agent container

Installs the Agent's Python/system dependencies and copies its source, binding and
configuration. Check CPU architecture, interpreter, writable locations and any
Agent-specific browser or Node requirements. The current KUMA overlay installs
its SDK with `python -m pip`; that selected interpreter must support pip.

### `.dockerignore` — what stays out of the build

Excludes secrets, host virtual environments, caches and results from the build
context. It must still include the source and configuration the image needs.
`-b` writes this file from ABB's template.

### `requirement.md` — what the evaluation should test

Describes the deployed Agent's purpose, observable behavior, actual tools and
limitations. KUMA requires YAML front matter plus Production Use Scenario,
Behaviors to Test, and Known Limitations or Prohibited Behaviors sections.
Its strategy group is selected from the current SDK catalog.

Describe present capabilities, not possible extensions. A search-only Agent can
explain a computation but cannot execute a sampler or persist a file. State what
it should do when a capability or required input is missing. This Profile guides
evaluation; it does not add tools, change the system prompt or modify saved Cases.

### `evaluation/` — optional supporting files

Only needed when the Profile references schemas or fixtures. It is not mandatory,
and there is no required `input-contract.json`. The current official KUMA generation
path accepts text; a locally valid structured schema does not establish remote
support. Native mapping remains in `agent.toml` and the binding.

### Registry and automatic records

`resources/registry.toml` is outside the unit. It stores each Agent's path, enabled
flag, `adapting`/`ready` state and `case` count. Final generation registers adapting;
certification controls promotion. `run` selects enabled ready Agents.

The importer also creates **`source-manifest.json` automatically** to record the
GitHub URL or canonical local path and its revision for reuse. It is an internal ABB record, not a
KUMA-required file or a document the user must prepare. Leave generated records
in place when continuing the add workflow.

Generation attempts and checkpoints live separately under
`cache/onboarding/<unit-name>-<path-digest>/`. `build-state.json` tracks reusable
work; attempt directories contain the plan, SDK catalog, per-file `steps/` and
`build-result.json`. These are also automatic records, not Agent source files.

## 4. Review and validate before execution

**Checkpoint — configured:** inspect every generated file, not just the success
message. Confirm source provenance and these boundaries:

- The descriptor resolves to the original graph. If the upstream has no
  `langgraph.json`, record a minimal added descriptor (for example
  `abb-langgraph.json`) explicitly in source provenance; do not rewrite the graph.
- The binding has a synchronous zero-argument factory and calls the real Agent.
  Preserve `config`/callbacks, native exceptions and raw output. Match the native
  UI's message append/active-agent lifecycle, isolate Cases and discard state on
  close. Do not keep mutable conversation state globally or swallow failed turns.
- The manifest's output field selects the actual reply while evidence retains
  the full state. Required text input is mapped truthfully; unsupported mandatory
  multi-field inputs are a stop condition.
- The image installs the upstream lockfile with a compatible interpreter. Keep
  host ABB dependencies separate from Agent dependencies. With uv, the project
  path, lockfile and runtime interpreter must agree; a separate `/opt/venv` avoids
  installing into a read-only source tree. Ensure runtime `python -m pip` works.
- Review the **effective SDK overlay**, including appended routes and copied
  binding/runtime files. Passing the outer TOML check alone is insufficient.
- The profile lists real tools, task data the caller must supply and unavailable
  operations. Current KUMA generation requires `input_type: text`, the three
  exact English section headings and a catalog-selected strategy group. Do not
  claim browsing, uploads, code execution or file persistence unless implemented.

After manual corrections, run the same static validator used by onboarding:

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
unit = Path("resources/agents/NN-name")
print(validate_unit(unit, plugin))
PY
```

This checks files and the installed SDK parser offline. It does not execute the
Agent or refresh/validate selection against the live catalog unless catalog
context is supplied. Generation validates against its saved fresh snapshot;
KUMA execution preflight checks service rules again. Static success is not an
execution pass. Add focused offline tests for nontrivial bindings: real adapter
boundary, session isolation, config forwarding, async if supported and errors.
Fixtures must be self-contained, or explicitly skip if an optional unit is absent.

## 5. Run one local smoke Case

For a configured text Agent, start small:

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

This uses the actual Docker Agent and model interception with fixed text Cases
and a local Judge. It needs Docker and configured model access; model tokens can
cost money. It needs no KUMA credential/credit, and is different from the
zero-credential offline echo demo. Its fixed Cases do not derive from the profile
and may not exercise article processing or specialist handoffs.

**Checkpoint — local:** retain the Suite path, detailed run directory, outputs,
trace status and Judge report. Require successful execution and host acceptance
before calling the integration runnable. Open view after this first run (section
7), including failures. An import check or fixture test is not a substitute.

If generic Cases omit required context, optionally use a source-backed native
input and `observe` after authorization. For a text binding, `native-input.json`
contains a JSON string; for another binding, match its actual schema. Include a
real article excerpt or other required business data, not “use the supplied text”
without supplying it.

```bash
python -m agentbench observe AGENT_ID --input native-input.json
```

Observe captures native execution without KUMA Case generation/Judge; model/tool
calls can still cost money. A focused observation does not convert a failed
benchmark into a pass. If the user explicitly requests KUMA directly, proceed to
section 6 after static review; report local validation as not performed if skipped.

## 6. Run a fresh KUMA evaluation

Review the deployed profile and current strategy selection, verify authorization
for KUMA/model use and evidence submission, then run one Case:

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

A local pass does not prove KUMA compatibility. A changed profile affects future
Cases only. Inspect the generated Case: does it supply required data, and does it
request actions the deployment actually supports? Save Case defects alongside
Agent findings; never edit original inputs, output or Judge evidence to force a pass.

While waiting, follow the existing run's progress through generation, Agent calls,
submission and Judge polling. An accepted asynchronous Judge request is not a
verdict. Do not launch duplicate evaluations while it polls. On timeout or error,
inspect saved completion/recovery state before deciding whether to resume or
retry. Respect replay safety and possible tool side effects; never force recovery
by changing safety flags. A new `evaluate` creates a new Suite and generally new
Cases, so it is not a controlled rerun of the old Case.

## 7. Open view and separate the outcomes

Open the viewer after the first local run, after KUMA, and before diagnosing a
failure, retrying it or reporting completion. In a headless environment, inspect
the same saved JSON/trace files and state that UI review was not performed.

```bash
python -m agentbench view results/suites/ACTUAL_SUITE_ID/events.json
```

Use the exact `Result saved` / `Open later` path from your command. The offline
demo instead prints a timestamped `OFFLINE_RESULT` file. Do not guess a filename
or reuse an old Suite. Open the full `View:` URL including its path; keep the server
running, and use Ctrl+C when finished. `--no-view` did not discard any results.

Review in order: **Suite → Case → each input and response → model/tool/handoff
trace → Judge and its evidence → execution/cleanup/host acceptance**. Compare what
the Agent said with what tools actually did. “Transferred successfully” is not
“specialist completed the task”; claiming a write is not evidence of a real write.

| Evidence | Interpretation and next action |
| --- | --- |
| Execution succeeded + host accepted + Judge pass | This Case passed; record its scope. Do not generalize to all capabilities. |
| Execution succeeded + host accepted + Judge issue | Integration executed; retain the behavioral finding. Do not rewrite prompts just to pass onboarding. |
| Native exception / execution failed | Not a successful run even if a Judge report arrived. Diagnose before promotion. |
| Partial traces / insufficient evidence / host rejected | Report the missing evidence separately. OTel complete alone does not mean all tool content was recorded. |
| Missing article/data or impossible Case action | Record a Case/profile limitation; assess supported Agent claims separately. Do not invent missing data. |

Detailed artifacts are under `results/observe/<run-id>/`: inspect `run.json`,
`evaluation/case.json`, `evaluation/inputs/`, `evaluation/manifest.json` and
`evaluation/judge/report.json` when present. Missing files identify an unfinished
phase; do not assume a verdict. A nonzero command exit can mean a Judge issue
rather than a crash. JSON exports alone are not standalone full-trace archives.

## 8. Decide whether certification is needed

`evaluate` does not promote the registry or change its Case count. If the intended
outcome includes selection by `run`, review the registry count and authorize the
additional execution, then use:

```bash
python -m agentbench certify AGENT_ID --sdk kuma --no-view
```

Certification runs the configured number of Cases; it does not simply approve
previous evaluation artifacts. All requested Cases completing without invocation
errors can promote `adapting` to `ready` even when Judge findings exist. Already
ready Agents return without another certification run; use `evaluate` for later
changes. Do not manually set ready to hide a blocked execution. If the user accepts
onboarding after a successful evaluation, report the actual registry state and
stop; do not run extra paid certification solely to change that label.

## 9. Diagnose at the failing boundary

Start from the first failing step and saved evidence. Use a minimal offline replay
where possible, changing one variable at a time: native graph vs binding, one vs
multiple tool calls, sync vs async, locked dependencies vs host environment.
Keep debugging scripts outside the distributable unit. Distinguish a deployment
fix from an upstream behavior change; propose the latter separately. Do not disable
interception, conceal errors or fabricate successful tool results.

| Symptom | Check / action / stop condition |
| --- | --- |
| `agentbench` missing or imports the wrong checkout | Activate this checkout's venv; use `python -m agentbench`; check editable installation before changing Agent code. |
| Docker unavailable, permission denied, no matching image architecture | Check `docker info` as the same user and the image platform. Obtain required environment permission; do not bypass isolation. |
| SDK listed but no onboarding hooks, or missing `kuma` import | Discovery is not capability/dependency validation. Use the supported generation SDK and install its pinned requirements. |
| Catalog/auth/network failure | Verify key presence, shell-over-file precedence, endpoint and connectivity without printing secrets; stop generation until resolved. |
| Structured-output rejection / `needs_input` / file conflict | Inspect plan and per-file records; use a suitable build model, factual answers or reviewed file corrections. Retry only the affected stage. |
| uv lock/project mismatch, missing pip, import failure in image | Check upstream Python range, lock location, selected interpreter, dependency isolation and COPY paths. Static checks cannot prove installation. |
| Overlay TOML error after valid outer config | An empty `tool_routes = []` can conflict with appended `[[llm_interception.tool_routes]]`; omit an unnecessary empty declaration after checking the effective config. Retain required routes/interception. |
| `INVALID_CHAT_HISTORY` during multiple handoffs | Match every AI tool-call ID with a ToolMessage; replay the actual graph offline. A single handoff passing does not prove parallel handoffs work. Preserve upstream failure evidence. |
| Judge reports no recovery or a claimed external action | Check whether the model actually received the earlier error and whether a corresponding tool exists/executed. Separate text claims, runtime state and evidence limitations. |
| Viewer blank / unavailable / old run | Build `web/dist`, use the printed full URL and exact result file, keep the server alive; check local port permission. Do not rerun a paid benchmark to repair the viewer. |

The Article Explainer onboarding exposed these distinctions: ordinary local chat
worked; one KUMA run hit a native parallel-handoff error; another completed but
received behavioral findings. Cases also omitted article text. These are diagnostic
examples, not a guaranteed verdict for another revision, model or Case, and no
strategy ID from that run should be reused without catalog review.

## 10. Handoff checklist and completion report

Report source/revision and unit path; generated vs manually corrected files;
commands and actual artifact/view paths; local/KUMA execution, host acceptance
and Judge separately; untested capabilities and known failures; registry state;
and Git status (committed/pushed/PR or local only). Separate code/doc changes from
`.venv`, credentials, images, caches, locks and results. Never commit secrets.

Stop once the agreed onboarding outcome has evidence. A behavior finding may be
a valid benchmark result, not unfinished integration work. Do not repeatedly run
until a lucky pass or silently repair the target Agent. If requested, stage the
reviewable changes and prepare a PR as a separate authorized step.

See [troubleshooting](Troubleshooting.md), [known issues](Documentation-Issue-Audit.md)
and [builder implementation](../agentbench/onboarding/build_agent_env/README.md).

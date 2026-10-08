# Add an Agent

English | [Français](otherLanguages/How%20To%20Add%20Agent.fr.md) | [日本語](otherLanguages/How%20To%20Add%20Agent.ja.md) | [中文](otherLanguages/How%20To%20Add%20Agent.zh-CN.md) | [한국어](otherLanguages/How%20To%20Add%20Agent.ko.md)

[How to start ABB](Guide.md) · [CLI reference](cli.md) · [Registry guide](Registry.md)

Follow these steps from the ABB checkout root with its virtual environment active: prepare the environment, import source, generate integration files, review them, and test the Agent. Replace SOURCE, AGENT_ID, NN-name and result paths with your actual values.

## 1. Prepare the environment

Install Git and Python 3.10+, then complete the startup guide linked above. Docker must be available to your user for Agent execution and certification. Install KUMA in the same virtual environment as ABB when using KUMA generation or validation:

```bash
python -m pip install -e .
python -m pip install "kuma-defuzex[otel]>=0.3.3"
git --version
agentbench --help
agentbench sdk list
docker info
```

`sdk list` lists plugins, not installed dependencies. Source import and configuration generation do not require Docker. Host SDK and container SDK installations are separate.

Copy `.env.example` to `.env` only if `.env` does not exist, then edit it locally. KUMA needs KUMA_API_KEY (or DEFUZEX_API_KEY); configuration generation uses OpenRouter and a model that supports strict structured output:

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate generation model:
# OPENROUTER_BUILD_MODEL=
```

The target Agent’s runtime model is configured separately: LangGraph integrations can use OpenRouter, DeepSeek or GLM; native ACP Agents use their own declared service credentials. See the startup guide. `--build-model` selects the generation model; `--model` selects ABB’s replacement target model for certification. Exported shell variables override `.env`. Keep keys out of source and generated files.

For the web viewer, use Node.js 20.19+ on 20.x or 22.12+, with npm, then build the frontend. Headless evaluation with `--no-view` does not require Node or `web/dist`.

```bash
cd web
npm ci
npm run build
cd ..
```

## 2. Import source and generate configuration

SOURCE must be an HTTPS GitHub repository URL, not a file or branch page, or an absolute local directory. GitHub imports the default branch; there is no `--revision` option. Local imports omit `.git` and record a content digest. First import the source:

```bash
agentbench agent add https://github.com/owner/repository
```

`agent add` also creates `ground_truth/.gitkeep` beside `agent/`, including when reusing an imported unit. The placeholder keeps the directory in Git; confirmed defects and evidence are prepared manually as described in [Ground Truth](Ground%20Truth.md).

Then generate integration files using the same source. Plain import repeated without `-b` or `-c` reports a duplicate; those options reuse the matching imported unit. Reuse does not refresh the snapshot from an edited source directory. For a local source, use `/absolute/path/to/local-agent`, or `"C:\work\local-agent"` in PowerShell.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma
```

`-b` supports LangGraph and ACP, generates and validates integration files, and registers the Agent as `adapting`; it does not build Docker. KUMA retrieves a current strategy catalog before planning. The bundled `local` SDK supports evaluation but has no onboarding validation hooks, so use KUMA for this generation workflow. If planning needs details, put factual deployment answers in UTF-8 `answers.txt` and repeat the command with `--answers answers.txt`. Completed valid files are retained after a failure. Inspect the saved `build-result.json` before retrying.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma --answers answers.txt
```

### If structured-output generation fails

Schema failures now report field paths, expected constraints and actual types.
Invalid JSON in model content reports decoder line/column and enters the same
bounded correction loop. Planning, file generation and review use their own
schemas; an invalid review response is corrected without regenerating a valid
candidate. File generation and review share the file's correction budget.
Provider envelope failures and unfinished responses remain terminal; check saved
diagnostics before changing provider settings or output budgets.
Preserve completed files and attempt records. A saved response is a record,
not an input to the next build. See
[Structured-output generation failures](Troubleshooting.md#structured-output-generation-failures)
for records, current null-field rules and correction-budget controls.

## 3. Understand the files

The Agent unit is placed under `resources/agents/NN-name/`. The command generates
integration files around the imported source; you do not need to create all of
these by hand before running it.

```text
resources/agents/NN-name/
├── agent/                   # Imported upstream or local source snapshot
├── agent.toml               # ABB execution configuration
├── bindings/                # LangGraph binding; not required for native ACP
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

### `bindings/*.py`

For LangGraph, the binding exports a synchronous zero-argument factory returning the real invokable Agent and adapts native input/output and lifecycle cleanup. ACP integrations use the native ACP command and protocol configured in `agent.toml`; a Python binding factory is not required. Neither form should replace the Agent’s behavior.

See [Writing LangGraph bindings](LangGraph%20Bindings.md) for file layout, invocation examples, config forwarding, native lifecycle handling and validation.

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

## 4. Review and validate the configuration

Review the generated entrypoint, native input/output mapping, dependencies, declared credentials and model/tool routes against the actual source. For LangGraph, check its graph descriptor and factory; for ACP, check its native command and session setup. The Profile must describe implemented tools, required caller data and limitations. After manual changes, run the onboarding validator (Bash example):

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/NN-name"), plugin))
PY
```

This checks installed files and the SDK parser without executing the Agent. Without a supplied catalog context it does not validate against the live strategy catalog. Static success does not establish runtime success.

## 5. Run one local smoke Case

Set `enabled = true` for the new Agent in the registry, then run one Case. `local` uses generic text Cases and a local Judge, with no KUMA backend credit. The target Agent and local Judge can still call a paid model. It does not certify integration or provide a KUMA behavioral assessment.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

## 6. Evaluate with KUMA

After the smoke test, use KUMA to generate a fresh Case, collect execution evidence and obtain a Judge report. This uses the configured model services and KUMA API.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

## 7. View the results

Use the exact file printed after `Result saved`, then open the complete `View:` URL and keep the command running. Use Conversation for inputs/outputs, Judge for findings, and Timing for execution and OTel traces. Execution completion and Judge verdict are separate: `issue` is a finding; `insufficient_evidence` alone is not a confirmed defect.

```bash
agentbench view results/suites/SUITE_ID/events.json
```

## 8. Certify the integration

To make an `adapting` Agent eligible for `run`, certify it while enabled. Certification performs a new execution using the registry Case budget; it does not approve previous evaluation artifacts. All requested Cases completing without invocation errors promotes the Agent to `ready`, even if Judge findings exist. An already ready Agent is not executed again; use `evaluate` for later tests. `-c` can also be used with `agent add`; it requires valid generated or manually prepared integration files and does not imply `-b`.

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
```

## 9. Results, recovery and troubleshooting

Suite plans, Cases and events are saved under `results/suites/SUITE_ID/`; detailed attempts usually live under `results/observe/RUN_ID/`. Always use the printed paths. `--results-dir DIR` chooses the ABB result root; `evaluate --output DIR` chooses SDK artifacts separately.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view --results-dir results/my-run
```

`resume` continues eligible unfinished work; `retry` targets one unfinished Case. `reuse` reruns saved inputs with fresh execution and judging, preserving original results. Case positions start at 1. In the viewer, Rerun this Case and Open reuse Suite provide the same workflow. Keep the process owning a reuse batch running; recovery is not guaranteed for unsafe or uncertain requests.

```bash
agentbench resume results/suites/SUITE_ID
agentbench retry results/suites/SUITE_ID --agent AGENT_ID --case 1
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 1
```

Export JSON saves a snapshot, not all traces or a standalone HTML report. Preserve the Suite and referenced attempt directories for complete evidence. Preview cleanup with `agentbench clean --dry-run`; stop runs and viewers before archiving history.

If the viewer reports Trace UI not built, build `web/`. For Docker errors, run `docker info` as the same user. For SDK import errors, install the SDK in ABB’s virtual environment. For model/key errors, check the selected service, model and shell-over-file precedence. For planning errors or needs_input, inspect the saved build record and supply factual answers.

[CLI reference](cli.md) · [Detailed troubleshooting](Troubleshooting.md)

# Add an Agent

Follow this order: **prepare the environment → run the add command → review the
files it creates**. A user or coding assistant can follow the same workflow.
Run all commands from the ABB repository root unless a command changes directory.
[中文操作指南](Guide.zh-CN.md#添加-agent) is also available.

## 1. Prepare the environment

### Install ABB and its host dependencies

Complete [ABB installation](../README.md#before-you-start) first. You need Git,
Python 3.10+ with an activated virtual environment, and a running Docker engine
for certification. Then install the selected SDK's host validation dependencies:

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

`sdk list` should show `kuma`; `docker info` must succeed as the same user who will
run ABB. Download/configuration generation alone does not require Docker, but
`-c` certification does. The host SDK installation and the SDK installed inside
an evaluation image are separate.

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

Key-retrieval links are in [the configuration guide](../README.md#configure-a-real-evaluation).
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

## 2. Run the add command

Replace the URL with the Agent's GitHub repository. Use the repository URL itself,
not a file or `/tree/branch` URL:

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`: generate and validate the integration files, then register the Agent as
  `adapting`. It does not mean “build the Docker image.”
- `-c`: build/run the configured Agent through certification. Successful execution
  of its configured Cases promotes it to `ready`; Judge findings can still exist.

ABB downloads source, plans the integration, saves each validated file, and then
asks for certification confirmation. Configuration generation and certification
can call paid services. Current automatic configuration supports **LangGraph**;
other frameworks need adapter support before this flow can run them.

To generate the files and inspect them before certification, omit `-c`:

```bash
agentbench agent add https://github.com/owner/repository -b
```

Without either flag, `agentbench agent add URL` only downloads source and lists
setup files; it does not generate configuration or register a runnable Agent.
The downloader records the default branch's revision; there is currently no
`--revision` option.

Useful options:

| Option | Use |
| --- | --- |
| `--no-view` | Certify without opening the viewer. Results are still saved. |
| `--build-model MODEL` | Model for generating integration files. |
| `--model MODEL` | Model for the Agent during certification. |
| `--answers answers.txt` | Supply text answers to questions from a previous plan. |
| `--with-observe` | With `-b`, generate native input prompts for `observe`. |
| `--build-settings settings.toml` | Override generation settings using a `[build]` table. |

Build-model precedence is `--build-model`, the settings file's `model`,
`OPENROUTER_BUILD_MODEL`, then `OPENROUTER_MODEL`. Read the
[packaged settings](../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)
before changing budgets, timeouts or retries.

## 3. Understand the files

The Agent unit is placed under `resources/agents/NN-name/`. The command generates
integration files around the downloaded source; you do not need to create all of
these by hand before running it.

```text
resources/agents/NN-name/
├── agent/                   # Downloaded upstream source
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — the Agent's own source

The downloaded repository lives here. Its graph, reasoning and tools remain the
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

The downloader also creates **`source-manifest.json` automatically** to record the
repository and revision for download reuse. It is an internal ABB record, not a
KUMA-required file or a document the user must prepare. Leave generated records
in place when continuing the add workflow.

Generation attempts and checkpoints live separately under
`cache/onboarding/<unit-name>-<path-digest>/`. `build-state.json` tracks reusable
work; attempt directories contain the plan, SDK catalog, per-file `steps/` and
`build-result.json`. These are also automatic records, not Agent source files.

## After generation

For an integration generated with `-b` alone, save input matching its binding in a
JSON file, then check native execution and certify:

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

Use the generated Agent ID. `observe` calls the Agent/model/tools without KUMA
Case generation or Judge; those model/tool calls can still be billed.
`evaluate --cases 1` does not change the registry's count; `certify` uses that count,
so check it first. Already-ready Agents return without a new certification run;
use `evaluate` to validate subsequent changes.

If generation stops, read `build-result.json` and the failed step, correct the
reported problem and rerun the same `-b` command. Completed files are retained and
revalidated; manual conflicts stop generation instead of being overwritten.
Use `--answers answers.txt` if planning asks for information.

For missing dependencies, unsupported deployments, trace/Judge failures or blocked
recovery, see [troubleshooting](Troubleshooting.md) and
[known issues](Documentation-Issue-Audit.md). Builder implementation details are
in [the developer guide](../agentbench/onboarding/build_agent_env/README.md).

# AgentBehaviorBench (ABB)

> **Before you run ABB:** install Python 3.10+, Docker Desktop or Docker
> Engine (running), and Node.js 20.19+ or 22.12+ to build the result viewer. The
> KUMA evaluation image installs its SDK from PyPI. Both bundled Agents need
> `KUMA_API_KEY` (or `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
> and `TAVILY_API_KEY`.

<p align="center">
  <img
    alt="AgentBehaviorBench — llama agents reviewing workflows"
    src="docs/figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  English |
  <a href="docs/otherLanguages/README.fr.md">Français</a> |
  <a href="docs/otherLanguages/README.ja.md">Japanese</a> |
  <a href="docs/otherLanguages/README.zh-CN.md">Simplified Chinese</a> |
  <a href="docs/otherLanguages/README.zh-TW.md">Traditional Chinese</a> |
  <a href="docs/otherLanguages/README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

AgentBehaviorBench runs registered AI agents in isolated runtimes, captures
their execution evidence, and evaluates the result through a selectable SDK.
SDK adapters are discovered from directories under `agentbench/sdk/plugin/`. With
one adapter it is selected automatically; with several, choose `--sdk NAME`.
This checkout currently includes KUMA. Results are written locally and can be
inspected in ABB's browser viewer.

ABB owns Agent selection, containers, concurrency, observation and local results.
Kuma owns the Case/Input/Submission/Report contract and calls the DefuzeX service
for official scenario generation and judging. A Case tests behavior in a scenario;
its Judge report is not a general intelligence score. A behavioral `issue` is a
completed evaluation finding. An invocation or evidence failure is recorded separately.

## Quick start

From the repository root, create a virtual environment and install ABB:

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
agentbench sdk list                   # Should list kuma without requiring credentials.
```

Try the complete local flow before configuring accounts:

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

This runs an echo Agent and deterministic local Judge without Docker, credentials,
or network. The `OFFLINE_RESULT=` line identifies the saved file. It demonstrates
the harness and viewer format; it does not test the official Kuma service.

The result viewer is built from `web/` and is not checked in. Build it once
before opening results; `run`, `evaluate` and `certify` start it after a run, and
`agentbench view` reopens a saved result:

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
agentbench view results/offline-demo.json
```

KUMA's adapter lives in `agentbench/sdk/plugin/kuma/`. Its evaluation image
installs `kuma-defuzex[otel]==0.2.7` from PyPI, as declared in the adapter's
`requirements.txt`; no local SDK source checkout is required. The distribution
is named `kuma-defuzex`, while Python code imports `kuma`.

Create the local environment file and add the required credentials:

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
# Required when using the KUMA evaluation SDK. KUMA_API_KEY is the name the KUMA
# SDK documents; ABB also accepts DEFUZEX_API_KEY, used only when KUMA_API_KEY is empty.
KUMA_API_KEY=

# Required for model calls made by Docker-based Agents. OPENROUTER_MODEL has no
# default: the value below is an example. Use a model your account can call.
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini

# Required by both bundled Agents (ReAct and Company Research) for web search.
TAVILY_API_KEY=
```

Install [Docker for your platform](https://docs.docker.com/get-started/get-docker/)
and start it. Check `docker info` before running an Agent. The checked-in registry
enables two Agents, both `ready`: `react-agent` and `company-research-agent`.
Evaluate one Case first. This calls the KUMA Case and Judge services, which are
charged to your key:

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

An Agent you add starts as `adapting`. Evaluate it the same way, and certify it only
after its native deployment requirements are satisfied:

```bash
agentbench certify NEW-AGENT
```

Certification requires successful execution and accepted evidence for every Case;
a Judge finding does not prevent readiness. Run every enabled ready Agent with:

```bash
agentbench run
```

ABB asks you to confirm the selected Agents, saves a result snapshot under
`results/`, and starts the local viewer. Use `--yes --no-view` for a non-interactive
or headless run:

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

To execute up to four Cases at once, set this single value in `.env`:

```dotenv
ABB_MAX_PARALLEL_CASES=4
```

The default is `1`. Cases from the same Agent can run together: one Agent with
four Cases can use all four workers. Across several Agents, the shared pool
never exceeds the configured Case limit. Inputs within one Case remain ordered.
ABB prepares each Agent's Case collection once, then gives each Case its own
runner, container session, working files, trace identity, and result.

The startup line shows the actual pool size, for example
`Case workers: 4 (configured: 4)`. Image caching and build coordination are
internal. Each Case keeps its own status, and final results are ordered by
Agent registration then Case index. Ctrl+C cancels active work, retains finished
Case results, and records cancelled or skipped Cases explicitly.

Directory SDK runs also retain a fixed plan and immutable Case files under
`results/suites/<suite-id>/` (or `suites/` beside a custom output base). Reopen the
printed `events.json` path to view all Cases and their attempt histories together.
The viewer can continue unfinished work or retry an eligible Case; its partial
report includes completed results even while other Cases are blocked.

```bash
agentbench resume results/suites/<suite-id>/events.json
agentbench retry results/suites/<suite-id>/events.json --agent react-agent --case 3
```

Completed Judge findings are retained, including `issue`; they are not retried
until a passing verdict appears. Safe transient execution failures have at most
two automatic retries by default. `--case-retries 0` disables these, and
`--retry-delay` sets the initial backoff for run/evaluate/certify. Unknown accepted
requests and unconfirmed cleanup remain blocked instead of duplicating work.
`agentbench reuse SUITE` starts a linked evaluation on the same Cases after you
change code or model; `resume`, `retry` and `reuse` each document their options
under `--help`.

Concurrent execution requires an SDK adapter supporting independent Case
execution and cancellation. Python callers pass
`ConcurrencySettings(max_parallel_cases=4)` to `SuiteRunner`; the library does
not implicitly load a dotenv file.

## Requirements and environment

| Requirement | Why it is needed |
| --- | --- |
| Python 3.10 or newer | ABB host CLI and harness. |
| Docker Desktop / Docker Engine | Docker Agents need a running engine before `run`, `evaluate`, `certify`, or `observe`. The offline demo does not. |
| Node.js 20.19+ or 22.12+ with npm | Builds the result viewer in `web/` once. Headless runs (`--no-view`) do not need it. |
| `KUMA_API_KEY` or `DEFUZEX_API_KEY` | Case and Judge access when using the KUMA SDK. `KUMA_API_KEY` wins when both are set. |
| `OPENROUTER_API_KEY` | Model traffic from Docker Agents is routed through ABB's interceptor to OpenRouter. |
| `OPENROUTER_MODEL` | Required model slug. `.env.example` contains an example value, not an implicit runtime default. Choose one your account can use. |
| `TAVILY_API_KEY` | Web-search credential for both bundled Agents, ReAct and Company Research. |

`.env` is ignored by Git. Environment variables already exported by the shell
override values in `.env`; `--env-file PATH` selects another dotenv file; and
`--model MODEL` overrides `OPENROUTER_MODEL` for one command.

Get model credentials from [OpenRouter keys](https://openrouter.ai/settings/keys),
and search credentials from the [Tavily dashboard](https://app.tavily.com/).
For Kuma credentials, follow the [official API key guide](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/sdk-guide.md#api-key)
and obtain an account key from your DefuzeX service administrator if none was issued.
ABB selects non-empty `KUMA_API_KEY` first, then `DEFUZEX_API_KEY` (an ABB alias),
and passes it explicitly to Kuma. A host SDK credential file is not mounted into
the container. Never put keys in CLI arguments, committed profiles, or reports.

The optional variables below are only needed when you want to identify
OpenRouter requests or use a compatible endpoint:

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

Installed as a package rather than run from this checkout, `agentbench` treats
the working directory as the project: `resources/registry.toml`, `.env`,
`results/` and `cache/` are resolved there, and `ABB_PROJECT_ROOT` selects
another directory. The package does not include the result viewer; build `web/`
in a checkout and set `ABB_WEB_ROOT` to its `web/dist`.

`ABB_MODEL_PROVIDER` selects the host model target provider (default
`openrouter`). Another provider is a package that registers a factory, called
with `model=`, in the `defuzex_agentbench.model_providers` entry-point group;
framework adapters register in `defuzex_agentbench.adapters` the same way.

## Included Agents

| Agent | Configured scope | Readiness |
| --- | --- | --- |
| ReAct (`react-agent`) | LangGraph reasoning and tool loop with native Tavily search | Enabled and ready in the checked-in registry. |
| Company Research (`company-research-agent`) | LangGraph multi-node company research with Tavily search; its Gemini and OpenAI calls are both routed to the configured model | Enabled and ready in the checked-in registry. |

Check `resources/registry.toml` for the current status; each Agent's source and
exact commit are recorded in its `source-manifest.json`. Readiness validates the
configured binding; it does not guarantee a passing Judge verdict for every
generated Case.

## CLI

Run `agentbench --help` or any command with `--help` for the installed CLI.
The most useful commands are:

| Command | Use |
| --- | --- |
| `agentbench run` | Evaluate every enabled `ready` Agent with the selected SDK. This is the default command. |
| `agentbench agent add https://github.com/owner/repository` | Download source into the next numbered Agent folder and print a JSON array of setup files. |
| `agentbench evaluate react-agent --cases 1` | Evaluate one enabled Agent on a chosen number of independent Cases. |
| `agentbench observe react-agent` | Run one enabled Agent with native input and save traces, without creating Cases or calling a Judge. |
| `agentbench certify NEW-AGENT` | Run an `adapting` Agent and promote it to `ready` only after certification succeeds. |
| `agentbench view results/benchmark.json` | Reopen a saved benchmark result in the local viewer (build `web/` first; see Quick start). |
| `agentbench resume SUITE` | Continue unfinished slots using saved Cases and original request state. |
| `agentbench retry SUITE --agent ID --case N` | Explicitly recover one unfinished Case; numbers start at 1. |
| `agentbench reuse SUITE` | Start a linked new evaluation using the same Cases under the current code. |
| `agentbench sdk list` | List adapter directories without importing SDK implementations. |
| `agentbench clean --dry-run` | Show the unreferenced entries under `results/` that `clean` would move into `cache/history-trash/`. Nothing is deleted. |

To begin onboarding a new Agent:

```bash
agentbench agent add https://github.com/owner/repository
```

Source is downloaded to `resources/agents/NN-repository/agent/`, using one more
than the largest existing directory number (`09` is followed by `10`). The outer
`source-manifest.json` records the repository URL and exact commit. Existing
Agent folders are never overwritten. Use `--agents-dir PATH` to select another
parent directory.

Standard output contains a sorted JSON array of paths relative to `agent/`:
LangGraph configs and their Python entrypoints, dependency files, Docker files,
README files and environment examples. Download status goes to standard error.
This first onboarding step does not import the downloaded code, install its
dependencies, generate benchmark configuration, or add an incomplete entry to
`resources/registry.toml`.

Optional generation and certification stages:

```bash
# Generate integration files with OpenRouter; register as adapting after static checks.
agentbench agent add https://github.com/owner/repository -b
# Generate, then use the existing container certification workflow.
agentbench agent add https://github.com/owner/repository -b -c
# Use configuration you wrote yourself; no AI configuration request.
agentbench agent add https://github.com/owner/repository -c
# Answer a previous plan's questions and reuse the downloaded source.
agentbench agent add https://github.com/owner/repository -b --answers answers.txt
```

`-b` means **generate the build configuration**, not build a Docker image. It reads
bounded setup files and local imports without executing the Agent, then sends
sanitized content to OpenRouter. Set `OPENROUTER_API_KEY` and
`OPENROUTER_BUILD_MODEL` (or `OPENROUTER_MODEL`) in the host environment or `.env`.
The model must support structured outputs. `--build-model` selects the generation
model; `--model` selects the separate certification model. The selected SDK's
PyPI requirements must be installed for its offline document validation.

`-b` first creates a source-based plan, then generates **one file per request**:
`agent.toml`, any required bindings (individually), `Dockerfile`, the optional input
schema, and `requirement.md`. Each file is validated and installed immediately,
before requesting the next. `.dockerignore` is written from a local template.
Later requests receive the plan and previously validated file contents.

The builders and their English prompts live in the corresponding subdirectories
of [`agentbench/onboarding/build_agent_env/`](agentbench/onboarding/build_agent_env/README.md).
Request settings and response schemas live in `openrouter_provider/assets/`.
Override budgets/timeouts/model with `--build-settings PATH`, containing a TOML
`[build]` table. `repair_attempts = 1` permits one additional paid correction per
stage; only the current file is repaired. Set it to zero to disable corrections.
HTTP transport retries are configured separately through `retries`.

Failure or Ctrl-C preserves completed files. Running the same `-b` command reuses
the source-matched plan in `onboarding/build-state.json`, validates existing files,
and generates only missing files. Existing manual files are never overwritten;
an invalid one stops the build with its path and reason. Answers or source changes
trigger fresh planning while preserving existing files. Ambiguous inputs or
unsupported network/protocol requirements produce questions.

Attempts are saved under `NN-name/onboarding/<attempt-id>/`: `context.json` lists
source files used/omitted, `plan.json` contains the plan, `steps/` records each
file's model responses, candidate, validation feedback and saved/reused status,
and `build-result.json` records completion or the failed stage. Registration
happens only after all files pass the final combined check. `-b` and `-c` reuse
manifest-matched downloads; plain `add` still rejects a duplicate checkout.

Certification builds and executes the container through the existing `certify`
command, including Case generation and Judge; it can call paid services. Use
`-y` to skip its confirmation and `--no-view` to omit the results viewer. Only
certification can promote `adapting` to `ready`; a Judge-reported behavioral issue
does not necessarily mean the integration failed. `--registry PATH` selects a
registry; a custom `--agents-dir` must remain inside that registry's repository.

Each configured Agent keeps its SDK evaluation specification in the outer
`requirement.md`. For KUMA, this document must follow the Agent Profile format:
YAML front matter and the required production-scenario, behaviors-to-test and
limitations sections. Case generation passes this exact file through
`agent_profile_path`; there is no separate `evaluation/profile.md`. Referenced
input schemas can remain under an optional `evaluation/` directory, with paths
relative to `requirement.md`. Agents do not need an `evaluation/` directory or
`input-contract.json`. Current Case inputs go directly to the framework adapter;
native field mapping stays in `agent.toml`, and conversation state belongs to the
Agent. Result artifacts under `results/.../evaluation/` are independent of this
optional source directory and remain unchanged.

Useful `run` options:

```bash
# Use an explicit model for this run.
agentbench run --model openai/gpt-4.1-mini

# Select a discovered adapter directory and pass it a JSON options file.
agentbench run --sdk kuma --sdk-options sdk-options.json

```

To add an SDK, create an adapter package with a `plugin.py` entry under
`agentbench/sdk/plugin/`; no central name list or package entry-point registration is
needed. `agentbench/sdk/plugin/kuma/` is the reference adapter.

`agentbench <command> --help` is the complete option reference.
[The agent onboarding guide](docs/How%20To%20Add%20Agent.md) summarizes the
`agent add` workflow above.

## Troubleshooting

These are the first-run failures, as `evaluate`, `run` or `certify` print them. All
but the model-name row stop before any KUMA request, so they cost nothing.

| Output | Cause | Fix |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker is not running, or `DOCKER_HOST` points at no daemon. | Start Docker Desktop or the Docker service until `docker info` succeeds. |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | No KUMA credential in the environment or `.env`. | Set `KUMA_API_KEY` in `.env`. |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | The variable holds something other than a KUMA key, such as an OpenRouter key. | Use the `dfx_` key issued for KUMA. |
| `AuthenticationError: Invalid API key.` after `GET defuzex.ai/… \| HTTP 401` | The KUMA key is wrong, revoked or for another Backend. | Replace the key; check `KUMA_BASE_URL` if you set one. |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | `OPENROUTER_MODEL` is unset; ABB has no default model. | Set `OPENROUTER_MODEL` in `.env`, or pass `--model`. |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY` (or `TAVILY_API_KEY`) | A credential the model upstream or the Agent's `agent.toml` requires is missing. | Add the named variable to `.env` or export it. |
| `LLM call 01 \| openrouter \| FAILED`, then `related network: upstream_error POST …` quoting the provider | The model upstream rejected the call, for example an unknown model name or a key without access to it. The Case was already generated and can still be judged and charged. | Use a model name your provider lists for your key. |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | The viewer has not been built in this checkout. | Run the printed command with Node.js 20.19+ or 22.12+. |

`agentbench clean` never deletes anything. It lists the unreferenced top-level
entries under `results/`, asks for confirmation, and moves them into
`cache/history-trash/<timestamp>/`. Saved Suites and the artifacts they reference
stay in place. To undo it, stop runs and viewers, then move the archived entries
back into `results/`.

## Overview

ABB is designed to make Agent evaluation reproducible. An Agent is declared in
the registry, adapted to ABB's runtime contract, evaluated with an SDK, and
saved with inspectable execution evidence. Agents progress from `adapting` to
`ready` only through the certification flow.

The execution path is:

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

![AgentBehaviorBench execution architecture](docs/figures/framework.png)

## Repository layout

- `resources/registry.toml` declares each Agent, its status, and its runtime.
- `resources/agents/` contains each Agent unit and its ABB configuration.
- `agentbench/cli/` provides the terminal commands.
- `agentbench/harness/` owns suite execution, results, and registry loading.
- `agentbench/runtime/` runs Agents locally or in Docker and intercepts model
  traffic for Docker runtimes.
- `agentbench/services/` contains runtime services shipped with AgentBench,
  including the Model Interceptor Docker build context.
- `agentbench/sdk/plugin/` contains SDK adapter packages, shared contracts, and directory discovery.
- `web/` contains the result viewer's sources; `npm run build` writes the
  `web/dist` files that the CLI serves.

## Development

Run the test suite after installing development dependencies:

```bash
python -m pytest
```

For repository conventions, see [AGENTS.md](AGENTS.md).

## License

MIT. See [LICENSE](LICENSE).

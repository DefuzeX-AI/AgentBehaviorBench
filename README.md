# AgentBehaviorBench (ABB)

> **Before you run ABB:** install Python 3.10+, Docker Desktop or Docker
> Engine (running), and the optional DefuzeX dependency. The bundled ready
> Company Research Agent needs `KUMA_API_KEY` (or `DEFUZEX_API_KEY`),
> `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and `TAVILY_API_KEY`.

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
  <a href="docs/otherLanguages/README.ja.md">日本語</a> |
  <a href="docs/otherLanguages/README.zh-CN.md">中文简体</a> |
  <a href="docs/otherLanguages/README.zh-TW.md">中文繁體</a> |
  <a href="docs/otherLanguages/README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

AgentBehaviorBench runs registered AI agents in isolated runtimes, captures
their execution evidence, and evaluates the result through a selectable SDK.
The default SDK is the built-in KUMA adapter. Results are written locally and
can be inspected in ABB's browser viewer.

## Quick start

From the repository root, create a virtual environment and install ABB with
the DefuzeX extra:

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[defuzex]"
```

Create the local environment file and add the required credentials:

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
# Required by the default KUMA evaluation SDK. DEFUZEX_API_KEY is accepted too.
KUMA_API_KEY=

# Required for model calls made by Docker-based Agents.
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini

# Required by the bundled Company Research Agent for web research.
TAVILY_API_KEY=
```

Start Docker, then run every enabled Agent whose registry status is `ready`:

```bash
agentbench run
```

ABB asks you to confirm the selected Agents, saves a result snapshot under
`results/`, and starts the local viewer. Use `--no-view` for a non-interactive
or headless run:

```bash
agentbench run --no-view --output results/benchmark.json
```

## Requirements and environment

| Requirement | Why it is needed |
| --- | --- |
| Python 3.10 or newer | ABB host CLI and harness. |
| Docker Desktop / Docker Engine | The bundled ready Agent runs in a Docker container. Docker must be running before `run`, `evaluate`, `certify`, or `observe`. |
| `KUMA_API_KEY` or `DEFUZEX_API_KEY` | Case and Judge access for the default KUMA SDK. |
| `OPENROUTER_API_KEY` | Model traffic from Docker Agents is routed through ABB's interceptor to OpenRouter. |
| `OPENROUTER_MODEL` | Model slug for the run; a default is provided in `.env.example`, but choose a model your account can use. |
| `TAVILY_API_KEY` | Web-search credential required by the bundled Company Research Agent. |

`.env` is ignored by Git. Environment variables already exported by the shell
override values in `.env`; `--env-file PATH` selects another dotenv file; and
`--model MODEL` overrides `OPENROUTER_MODEL` for one command.

The optional variables below are only needed when you want to identify
OpenRouter requests or use a compatible endpoint:

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

Run `agentbench --help` or any command with `--help` for the installed CLI.
The most useful commands are:

| Command | Use |
| --- | --- |
| `agentbench run` | Evaluate every enabled `ready` Agent with the selected SDK. This is the default command. |
| `agentbench evaluate company-research-agent --cases 1` | Evaluate one enabled Agent on a chosen number of independent Cases. |
| `agentbench observe company-research-agent` | Run one enabled Agent with native input and save traces, without creating Cases or calling a Judge. |
| `agentbench certify react-agent` | Run an `adapting` Agent and promote it to `ready` only after certification succeeds. |
| `agentbench view results/benchmark.json` | Reopen a saved benchmark result in the local viewer. |
| `agentbench sdk list` | List built-in and installed evaluation SDK plugins. |
| `agentbench clean --dry-run` | Show the local result history that would be moved to a recoverable archive. |

Useful `run` options:

```bash
# Use an explicit model for this run.
agentbench run --model openai/gpt-4.1-mini

# Select a built-in or installed SDK and pass it a JSON options file.
agentbench run --sdk kuma --sdk-options sdk-options.json

# Print sanitized model activity while retaining the normal result artifact.
agentbench run --llm-trace terminal
```

See [the CLI reference](docs/CLI.md) for the complete command and option
reference, and [the agent onboarding guide](docs/How%20To%20Add%20Agent.md) to
add another Agent.

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
- `agentbench/sdk/` contains built-in SDK adapters and plugin discovery.

## Development

Run the test suite after installing development dependencies:

```bash
python -m pytest
```

For repository conventions, see [AGENTS.md](AGENTS.md) and
[docs/AGENTS.md](docs/AGENTS.md).

## License

MIT. See [LICENSE](LICENSE).

# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench (ABB)"
    src="figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  English |
  <a href="otherLanguages/README.fr.md">Français</a> |
  <a href="otherLanguages/README.ja.md">日本語</a> |
  <a href="otherLanguages/README.zh-CN.md">中文简体</a> |
  <a href="otherLanguages/README.zh-TW.md">中文繁體</a> |
  <a href="otherLanguages/README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## News

- AgentBehaviorBench (ABB) now runs registered LangGraph agents through the DefuzeX SDK
  `get_input()` / `submit()` handshake.

## Overview

AgentBehaviorBench (ABB) is a benchmark for evaluating AI agents on end-to-end tasks
that require calling a target Agent, collecting its outputs and execution trace,
and judging whether it completed the requested workflow correctly.

Given a registered Agent and a benchmark Case, AgentBehaviorBench (ABB) runs the Agent through
a trusted host harness. The harness can launch framework-specific or
containerized Agents, transparently route model traffic through a
credential-safe Model Interceptor into a run-selected OpenRouter model, record
each SDK input and Agent response in a JSON event snapshot,
and submit the completed run to the DefuzeX Judge.

AgentBehaviorBench (ABB) is designed to make Agent evaluation reproducible. Agents are
declared in a registry, adapted through framework adapters such as LangGraph,
certified from `adapting` to `ready`, and included in default benchmark runs only
after certification succeeds.

The current execution flow is:

```text
registry.toml
-> SuiteRunner
-> BenchmarkRunner
-> DefuzeX SDK Run
-> Agent Adapter / Runtime
-> Judge Report
```

The repository includes:

- `agentbench/cli`: terminal entry point and progress output.
- `agentbench/harness`: SDK handshake, suite execution, results, and registry.
- `agentbench/adapter`: framework-neutral adapter contract and LangGraph support.
- `agentbench/runtime`: local and Docker runtime integration.
- `resources/agents`: user-named Agent units, with source in `agent/` and ABB
  configuration alongside it. See [Agent directory layout](docs/Agents/Layout.md).
- `services/model-interceptor`: transparent TLS, authentication, streaming, and
  OpenRouter routing and model Trace service for Docker runs.

![AgentBehaviorBench (ABB) framework](figures/framework.png)

## Setup

AgentBehaviorBench (ABB) requires Python 3.10 or later. Evaluation SDKs can be
selected with `BenchmarkRunner(sdk=your_sdk, sdk_options={...})`,
`SuiteRunner(sdk=your_sdk, sdk_options={...})`, or CLI `--sdk MODULE[:OBJECT]`.
See [SDK selection and its interface](docs/SDK.md) for a complete offline example.

DefuzeX remains the default evaluation integration and is now an optional
dependency: install this checkout with `python -m pip install -e ".[defuzex]"`
or install the local SDK separately. The following setup describes that default.
The SDK provides the benchmark protocol used by AgentBehaviorBench (ABB): it parses benchmark
requirements, creates DefuzeX Cases, drives each SDK input, records evidence,
and submits completed runs for judging.

Create and activate a virtual environment from the parent workspace that
contains this repository:

```powershell
cd <workspace-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install AgentBehaviorBench (ABB) in editable mode:

```powershell
python -m pip install -e .\defuzeX_AgentBench
```

### Internal SDK Build

This repository currently depends on the internal DefuzeX SDK `dev` branch.
Until the SDK is published for normal package installation, if `Defuze-SDK` has
not been cloned locally yet, clone it from the SDK `dev` branch
(`https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev`) next to
`defuzeX_AgentBench`, then install it into the same `.venv`:

```powershell
cd <workspace-root>
git clone --branch dev --single-branch https://github.com/DefuzeX-AI/Defuze-SDK
python -m pip install -e .\Defuze-SDK
python -m pip install -e .\defuzeX_AgentBench
```

A typical source checkout has `Defuze-SDK` and `defuzeX_AgentBench` as sibling
directories under the same parent workspace, both installed in editable mode.

> [!NOTE]
> PAT means Personal Access Token. If the internal DefuzeX SDK repository is
> private, GitHub may require a PAT when cloning it over HTTPS. Treat the PAT
> like a password: keep it out of source files, README examples, notebooks, and
> committed `.env` files.

## Usage

After installing AgentBehaviorBench (ABB), start it from the benchmark workspace with the
launcher script:

```powershell
cd <workspace-root>
.\.venv\Scripts\Activate.ps1
python .\run_agentbench.py
```

You can also run the package directly from the AgentBehaviorBench (ABB) repository:

```powershell
cd <workspace-root>\defuzeX_AgentBench
python -m agentbench
```

To save a run and inspect live benchmark events in the local result viewer, pass
an output path:

```powershell
python -m agentbench --output results\result.json
```

Without `--output`, AgentBehaviorBench (ABB) runs in the terminal and does not create a JSON
result artifact. With `--output`, AgentBehaviorBench (ABB) writes an atomically updated JSON result
file and starts the local viewer so you can refresh and inspect events while the
benchmark is running.

Set a DefuzeX API key when using official Case or Judge providers:

```powershell
$env:DEFUZEX_API_KEY = "dfx_<public-id>.<secret>"
```

Docker Agents route model traffic through OpenRouter. Configure its key and
choose one model for the complete benchmark run:

```powershell
Copy-Item .env.example .env
# Edit .env locally; it is ignored by Git and loaded automatically by the CLI.
```

PowerShell environment variables override `.env`, and
`python -m agentbench run --model <slug>` overrides `OPENROUTER_MODEL`.

Run the test suite:

```powershell
python -m pytest
```

For more agent-facing instructions, start with [AGENTS.md](AGENTS.md). The
longer documentation guide is in [docs/AGENTS.md](docs/AGENTS.md).

## How to Add Agents to Testing

If you want to add your own Agent to the benchmark, ask an agent to read
[docs/How To Add Agent.md](docs/How%20To%20Add%20Agent.md) and follow the
onboarding flow documented there.

AgentBehaviorBench (ABB) provides the pieces needed to turn an external Agent project into a
repeatable benchmark target: registry-based discovery, framework adapters,
Docker runtime support, model credential routing through the Model Interceptor,
JSON result snapshots, local result viewing, and certification from
`adapting` to `ready`. This gives you a consistent way to compare Agents across
the same DefuzeX Cases while keeping runtime behavior, outputs, and judgment
evidence inspectable.

## Citation and License

MIT License. See [LICENSE](LICENSE).

If you find our work helpful, please cite it as follows:

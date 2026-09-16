# Add an Agent

Run from the ABB checkout with its `.venv` activated. Complete
[host installation and viewer setup](../README.md#before-you-start) first.
[中文操作与接入指南](Guide.zh-CN.md#添加-agent) is also available.

## 1. Check the actual deployment requirements

Inspect the upstream README, dependency manifests, tool definitions and entrypoint:

| Requirement | What to verify |
| --- | --- |
| Framework and entrypoint | A real invokable Agent/graph, factory, input and final output. Current automatic generation supports LangGraph; a web UI alone is not an Agent entrypoint. |
| Runtime | Python/Node versions, OS packages, CPU architecture, browser binaries, writable directories and memory needs belong in the Agent image/environment. Host Node for ABB's viewer does not install an Agent's browser or MCP server. |
| Models | Native protocol, tool calling and interception routes. The build model and tested Agent model are separate settings. |
| Tools and services | Exact tools, external APIs, databases, MCP processes, fixtures and required keys. Installing a database driver does not start a database. |
| State and side effects | Session state, writes and external actions. Do not mark `replay_safe` true just to enable retries. |
| Evaluation scope | Tasks the deployed tools can perform, available evidence, and what the Agent should do when data or capabilities are missing. |

The current environment service provider includes MongoDB; this does not imply
arbitrary Compose stacks, browsers or other databases are provisioned automatically.
Inspect generated environment configuration and real startup. Source discovery
does not guarantee every build input, submodule or dependency was captured.

## 2. Download, then configure

```bash
agentbench agent add https://github.com/owner/repository
```

Use a repository HTTPS URL, not a file or `/tree/branch` URL. Plain `add` downloads
the default branch into the next numbered `resources/agents/NN-name/agent/`, saves
`source-manifest.json` with its revision, and prints discovered setup paths as JSON.
It does not install dependencies, register a ready Agent or execute it. Inspect
the saved source revision; the CLI currently has no `--revision` option.

For assisted configuration with KUMA:

```bash
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
agentbench agent add https://github.com/owner/repository -b
```

`.env` needs `KUMA_API_KEY` (or ABB's `DEFUZEX_API_KEY` alias) for the strategy
catalog, plus `OPENROUTER_API_KEY` and a build model selected through
`--build-model`, a `[build].model` setting, `OPENROUTER_BUILD_MODEL`, or the
`OPENROUTER_MODEL` fallback, in that order.
The build model must support strict structured outputs. A working chat model is
not necessarily compatible with `-b`.

`-b` means **generate build configuration**, not build or launch the container.
It obtains SDK context, plans from source, generates each file separately,
validates it, and saves it before continuing. Final validation registers `adapting`.
Source context is sent to the configured model service; `.env` is excluded.

```text
resources/agents/NN-name/
├── agent/                   # Upstream source; preserve behavior
├── source-manifest.json     # Source URL and revision
├── agent.toml               # Runtime, adapter, routes and environment
├── bindings/                # Outer factory and native boundary adaptation
├── Dockerfile
├── .dockerignore
├── requirement.md           # SDK evaluation profile
└── evaluation/              # Optional referenced schema/fixtures
```

Bindings belong outside `agent/`. A generated factory is synchronous, accepts no
arguments and returns the real invokable object. Keep reasoning/tool execution
in the upstream Agent. Translate boundary formats without inventing answers or
silently removing tools to make certification pass.

KUMA's `requirement.md` needs YAML front matter and its three required sections.
The current official generation path accepts text inputs; native mapping belongs
in `agent.toml`/the binding. Multiple required business fields that cannot be
obtained from text need a reviewed input design, not invented values. There is no
mandatory `evaluation/` folder or `input-contract.json`.

The Profile must describe **deployed** tools, missing capabilities, required data,
observable behavior and honest refusal/clarification behavior. Future extensions
are not installed tools. A search-only Agent can explain a computation but cannot
execute a sampler, persist a file or configure a real concurrency controller.
A Profile defines evaluation expectations; it does not add tools or inject a
system prompt. Choose a strategy group from the fresh SDK catalog; the attempt's
`sdk-context.json` records that snapshot. Do not copy an old group ID from an issue.

## 3. Inspect and continue generation

```bash
# Put answers to a plan's questions in a local text file.
agentbench agent add https://github.com/owner/repository -b --answers answers.txt
# Optionally generate native Observe prompts from the input definition.
agentbench agent add https://github.com/owner/repository -b --with-observe
```

Records live under `cache/onboarding/<unit-name>-<path-digest>/`, relative to the
registry's project root, **outside the Agent unit**. `build-state.json` tracks the
plan and file hashes. Attempts contain source context, plan, SDK context,
per-file `steps/` and `build-result.json`.

Rerunning `-b` reuses source-matched state and revalidates files. It preserves manual
files and stops on conflicts. Fix the reported file rather than deleting the entire
Agent/cache. Partial work remains after failure or Ctrl+C. Plain `add` rejects
duplicate source directories; `-b`/`-c` can reuse matching downloads.

`--build-settings PATH` accepts a TOML `[build]` table. Read
[the packaged defaults](../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)
before changing timeouts, context/output budgets or retry counts. A larger timeout
does not solve unsupported schemas. `--build-model` selects the generation model;
`--model` selects the certification model.

## 4. Verify native execution, then certify

Save native input matching the binding in a JSON file. Bundled ReAct accepts, for
example, `{"message":"Search for LangGraph documentation and summarize it."}`.
Do not reuse that shape for an Agent with a different contract.

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

`observe` calls the Agent/model/tools without Case generation or Judge. Its model
and tool calls can be billed. Resolve native startup, input and route failures here
first. `evaluate --cases 1` does not change the registry's Case count; `certify`
uses that registered count, so check it before starting.

The combined flow, or certification of manually prepared files:

```bash
agentbench agent add https://github.com/owner/repository -b -c --no-view
agentbench agent add https://github.com/owner/repository -c --no-view
```

Certification can use paid services. It promotes `adapting` to `ready` when all
requested Cases complete without invocation errors; Judge issues alone do not
prevent promotion. Already-ready registrations return without a new run: use
`evaluate` to validate changes. `enabled` independently controls selection; `run`
includes only enabled ready Agents. Do not edit readiness to claim acceptance.

## Troubleshooting by file

| File / stage | Check |
| --- | --- |
| `agent.toml` | Real entrypoint, input mapping, timeout, declared env keys, model/tool routes. Every required input needs a truthful source. |
| `bindings/*.py` | Factory imports, graph API version, final output and lifecycle. Valid syntax does not prove the graph loads. |
| `Dockerfile` | Base architecture, dependencies, selected Python interpreter, binding COPY and writable locations. The SDK overlay currently expects `python -m pip`. |
| `.dockerignore` | Include required source/config/bindings; exclude `.env`, host venvs, caches and results. |
| `requirement.md` | Official parser validity, current strategy coordinates and factual capability boundaries. Installation/plumbing details are not behavioral test criteria. |
| Optional input schema | Relative path and fields match the binding. Local parsing does not prove remote generation supports that input type. |
| `.env` | Key precedence, build vs Agent model, and required tool keys. Never paste values into bug reports. |
| `resources/registry.toml` | Unit path, ID, enabled flag, lifecycle state and Case count. |
| `cache/onboarding/…` | Failed file/stage and validation feedback before retrying. |

Known runtime defects are not fixed by documentation: image-local dependencies
may be hidden by a bind mount ([#66](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/66));
an interpreter without pip can fail the SDK overlay
([#65](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/65)). Native Linux
ownership/recovery also needs real acceptance checks. Preserve startup errors
and artifacts. See [troubleshooting](Troubleshooting.md),
[the issue audit](Documentation-Issue-Audit.md) and
[builder internals](../agentbench/onboarding/build_agent_env/README.md).

# AgentBehaviorBench (ABB)

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

ABB is for developers evaluating how an Agent behaves in a concrete task: what
it was asked, what it actually did, and whether the evidence supports its answer.
ABB runs Agents, isolates Cases, captures traffic and traces, and saves results.
The **KUMA SDK** defines Cases and submits evidence to the **DefuzeX service** for
Case generation and judging. OpenRouter supplies the tested Agent's model;
services such as Tavily supply its tools. These are separate accounts and roles.

A completed evaluation may receive `pass`, `issue`, or `insufficient_evidence`.
An `issue` is a behavioral finding; it is not automatically a container failure.
See [results and troubleshooting](docs/Troubleshooting.md) and the
[Chinese operation guide](docs/Guide.zh-CN.md).

## Before you start

Use a **source checkout with an editable installation** for the complete CLI,
Agent resources and viewer. A standalone Python wheel does not include the
repository's `resources/` or `web/dist/` assets.

| Install on the host | Needed for | Verify |
| --- | --- | --- |
| Git | Clone ABB and download Agent repositories | `git --version` |
| Python 3.10+ with pip and venv | CLI, harness and offline demo | `python3 --version` |
| Docker Desktop or Docker Engine, running and accessible to your user | Docker Agent execution and official evaluation | `docker info` |
| Node.js **20.19+ in the 20.x line, or 22.12+** and npm | Build the browser viewer; optional for headless runs | `node --version` and `npm --version` |
| A browser | Open the local viewer URL | Use the exact URL printed by ABB |

Node's version requirement comes from the locked Vite dependencies in
[web/package-lock.json](web/package-lock.json). Node is needed to build or develop
the viewer; the normal `agentbench view` server is Python and serves `web/dist`.
Installing Python dependencies does **not** install or build the web application.

- **macOS:** install and start [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/).
  Agent base images and binary dependencies must support your CPU architecture.
- **Linux:** install [Docker Engine](https://docs.docker.com/engine/install/), then follow
  its [post-installation guidance](https://docs.docker.com/engine/install/linux-postinstall/)
  so the same user running ABB can access Docker. `docker info` must succeed.
- **Windows:** use [Docker Desktop with WSL 2](https://docs.docker.com/desktop/features/wsl/)
  and a Linux distribution for the shell commands below. Native PowerShell and
  individual Agent images have not been verified by this documentation update.
- The offline demo uses an in-process Agent and needs no Docker. This is not an
  automatic fallback for Docker registrations. Agent Python packages, browsers,
  database services, local models and tool credentials are **per-Agent requirements**;
  downloading a repository does not provision them.

First installation requires access to Python/npm registries; Docker builds also
need image registries and Agent dependency sources. Official runs require access
to DefuzeX, OpenRouter and the selected Agent's permitted tool endpoints. For
custom endpoints and network failures, see [troubleshooting](docs/Troubleshooting.md).

## Install and verify without credentials

```bash
git clone https://github.com/DefuzeX-AI/AgentBehaviorBench.git
cd AgentBehaviorBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
agentbench --help
agentbench sdk list
```

`--help` should list commands including `run`, `agent`, `observe` and `view`.
`sdk list` should list `kuma`; discovery does not test credentials or install the
SDK. If the console command points at an old checkout, activate this environment
and repeat `python -m pip install -e .`.

Try the harness without Docker, keys or model calls:

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

Expected summary: `Case execution: 1/1 completed | Judge: pass=1`.
The `OFFLINE_RESULT=` line prints the **actual timestamped file path**. It is a
local echo Agent with a deterministic Judge, not an official KUMA acceptance run.

## Build and open the viewer

```bash
cd web
npm ci
npm run build
cd ..
# Replace the example path with the exact OFFLINE_RESULT path printed above.
agentbench view results/offline-demo-YYYYMMDD-HHMMSS.json
```

The build creates `web/dist/index.html` and its assets. A fresh clone has no
`web/dist`; rebuild after changing frontend code or dependencies. Open the exact
`View:` URL, including its Suite path. ABB defaults to local port 8765 and selects
an available port if occupied. Keep the command running while viewing results;
Ctrl+C stops the viewer. You do not need `npm run dev` for normal benchmark use.

Use `--no-view` with `run`, `evaluate` or `certify` to save results without starting
the viewer; Node and the frontend build are then unnecessary. Build later and
open the saved result. Frontend development instructions are in [web/README.md](web/README.md).

## Configure a real evaluation

Copy the template once; keep an existing `.env` when upgrading:

```bash
cp .env.example .env
```

Edit `.env` locally:

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
ABB_MAX_PARALLEL_CASES=1
```

| Setting | Meaning / where to obtain it |
| --- | --- |
| `KUMA_API_KEY` | Official Case/Judge access. See [DefuzeX SDK documentation](https://defuzex.ai/documentation?view=sdk) and [KUMA documentation](https://github.com/DefuzeX-AI/KUMA-DefuzeX). Use the key issued for that service. |
| `DEFUZEX_API_KEY` | ABB's alternative name for the same service credential. A nonempty `KUMA_API_KEY` takes precedence; only one is needed. |
| `OPENROUTER_API_KEY` | Model access from [OpenRouter API keys](https://openrouter.ai/settings/keys). |
| `OPENROUTER_MODEL` | **Required model slug**, not a key. The value in `.env.example` is an example, not a runtime fallback. Select a model supported by your account and the Agent's tool/protocol needs. |
| `TAVILY_API_KEY` | Search access from [Tavily](https://app.tavily.com/) for Agents using its search tool. |
| `ABB_MAX_PARALLEL_CASES` | Positive integer; default 1. For example 4 permits up to four concurrent Cases across all selected Agents. |

These commands need different services:

| Action | Docker | KUMA key | OpenRouter key + model | Agent tool keys |
| --- | --- | --- | --- | --- |
| CLI help, SDK discovery, offline demo, saved-result viewer | No | No | No | No |
| `agent add URL` (download only) | No | No | No | No |
| `agent add URL -b` with KUMA | No | Yes, for strategy catalog | Yes, structured-output build model | Not executed during generation |
| `observe` a Docker Agent | Yes | No | Yes | As declared by that Agent |
| `evaluate`, `run`, `certify` with KUMA and Docker Agents | Yes | Yes | Yes | As declared by that Agent |

Model, search and evaluation services have separate quotas/billing. An API key's
existence does not prove the chosen model or endpoint is usable. `observe` is a
useful native-input check before paying for Case generation; its model/tool calls
can still be billed.

The CLI loads the checkout's `.env`. Exported shell variables take precedence,
including an exported empty value; `--env-file PATH` selects a different file.
`--model MODEL` overrides the Agent model for that command. Python library callers
supply their environment explicitly. `.env` is not copied wholesale into Agent
containers: the runtime resolves declared keys and the interceptor supplies model
credentials. The bundled ReAct route therefore does not require a real
`ANTHROPIC_API_KEY` on the host.

KUMA's distribution is `kuma-defuzex`; the Python import is `kuma`. Evaluation
images install the pinned package from
[the plugin requirements](agentbench/sdk/plugin/kuma/requirements.txt). For `-b`
profile validation and host SDK inspection, install the same requirements in
**this host venv**:

```bash
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
python -c "from importlib.metadata import version; import kuma; print(version('kuma-defuzex')); print(kuma.__file__)"
```

Do not use the old `.[defuzex]` extra or a local SDK checkout as a substitute.
An IDE must select this same `.venv` interpreter to resolve KUMA imports.

## Run one Agent, then a Suite

Inspect available enabled Agents before starting a run:

```bash
agentbench observe --list
agentbench evaluate react-agent --cases 1 --no-view
```

The single-Case example asks for confirmation, then runs Case generation, Agent
execution, evidence capture and Judge. One Case can contain multiple ordered
inputs. `--max-steps` can bound the SDK's input execution, but truncating a scenario
may affect whether Judge has sufficient evidence.

`resources/registry.toml` is authoritative for IDs, `enabled`, `status` and `case`
counts. The source units currently present are ReAct (Tavily search) and Company
Research (company research); both declare Tavily access. Do not infer readiness
or enabled state from an old README or campaign report.

- `adapting`: integration has been registered but needs certification.
- `certify AGENT_ID`: executes the configured Cases and promotes to `ready` only
  when execution completes successfully. Judge issues can coexist with readiness.
  Calling it on an already-ready Agent returns without a new certification run.
- `run`: selects all enabled `ready` Agents and uses each registry `case` count.

After the single-Agent check:

```bash
agentbench run
# Non-interactive and headless:
agentbench run --yes --no-view --output results/benchmark.json
```

Set `ABB_MAX_PARALLEL_CASES=4` for up to four concurrent Cases. Cases from one Agent
can share the pool; inputs inside each Case stay ordered. Each Case has its own
execution session and artifacts. This setting does not limit tool concurrency
inside an Agent. More workers consume more Docker resources and service quota.

## Results, recovery and sharing

Use the printed paths, not a guessed filename: output bases may be timestamped.
A managed Suite keeps its plan, Cases and event history under
`results/suites/<suite-id>/`; detailed attempts are under `results/observe/<run-id>/`.
The viewer shows Agent/Case rows, attempt history, execution state, Judge verdict,
inputs/outputs and available OTel details. A completed `issue` is not retried until
it becomes a `pass`.

```bash
agentbench view results/suites/<suite-id>/events.json
agentbench resume results/suites/<suite-id>/events.json
agentbench retry results/suites/<suite-id>/events.json --agent react-agent --case 3
agentbench reuse results/suites/<suite-id>/events.json
```

`resume` continues eligible unfinished work; `retry` targets an unfinished Case
(numbered from 1); `reuse` creates a new linked Suite using saved Cases and current
code. Recovery depends on saved request state, replay safety and cleanup. Some
uncertain requests remain blocked. These commands do not promise every failure
can be retried. `--case-retries 0` disables automatic Case retries for new runs;
inspect command help for backoff options.

**Export current report** downloads a JSON snapshot, not a standalone HTML report
or an archive of every trace. `web/dist/index.html` also depends on its assets and
local APIs; sending that HTML alone does not share the evaluation. Preserve the
Suite and its referenced attempt directories together when transferring full
results; their saved paths may need relocation. See [sharing and failure diagnosis](docs/Troubleshooting.md).

## Add your Agent

Start with [the Agent onboarding guide](docs/How%20To%20Add%20Agent.md), or
[the Chinese guide](docs/Guide.zh-CN.md#添加-agent).

```bash
agentbench agent add https://github.com/owner/repository
agentbench agent add https://github.com/owner/repository -b
agentbench agent add https://github.com/owner/repository -b -c
```

Plain `add` downloads source. `-b` generates and validates integration files one at
a time; `-c` runs certification. Downloaded does not mean configured, and generated
does not mean executable. Framework support and external services must be checked
before committing to a full run. Current automatic configuration supports LangGraph.

## CLI and repository layout

Run `agentbench --help` and `agentbench COMMAND --help` for the current options.
`observe` uses native input without Judge; `sdk list` discovers plugins;
`clean --dry-run` previews recoverable history cleanup.

```text
AgentBehaviorBench/
├── agentbench/
│   ├── cli/                 # Commands and local viewer server
│   ├── onboarding/          # Source discovery and integration generation
│   ├── adapter/             # Native framework invocation
│   ├── harness/             # Case scheduling, retries and results
│   ├── runtime/             # Containers and interception
│   └── sdk/plugin/          # Evaluation SDK integrations
├── resources/
│   ├── registry.toml
│   └── agents/              # Upstream source + outer integration files
├── examples/               # Offline demonstration
├── web/                    # React viewer; npm builds dist/
├── docs/
├── results/                # Generated Suite and execution artifacts
└── cache/                  # Generated onboarding records and archives
```

## Development

Install test tools explicitly; there is no `dev` dependency extra:

```bash
python -m pip install pytest
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
python -m pytest
cd web
npm ci
npm test
npm run build
```

Some tests require separate service dependencies, Docker, or Agent fixtures; read
the relevant module instructions and report missing prerequisites separately.
See [AGENTS.md](AGENTS.md) for contributor boundaries and
[the documentation issue audit](docs/Documentation-Issue-Audit.md) for this revision's
upstream findings and remaining limitations.

## License

MIT. See [LICENSE](LICENSE).

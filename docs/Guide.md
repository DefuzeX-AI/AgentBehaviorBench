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
[README](../README.md#before-you-start).

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

The SDK list should contain `kuma`. The demo uses a local echo Agent and deterministic
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
running; Ctrl+C stops it. Port 8765 is the default; ABB selects an available port
when it is occupied. Rebuild after frontend changes. Normal use does not require
`npm run dev`.

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

See [credential links and the command/service matrix](../README.md#configure-a-real-evaluation).
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
agentbench run --yes --no-view --output results/benchmark.json
```

A Case can contain multiple ordered inputs. `run` selects enabled ready Agents and
uses their registry `case` counts. Readiness certifies integration, not a guaranteed
Judge pass. Check [the registry](../resources/registry.toml) for current selection.

`ABB_MAX_PARALLEL_CASES=4` permits up to four Cases across the Suite, including
Cases of the same Agent. It does not limit tool concurrency inside an Agent.

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
Detailed attempts live under `results/observe/<run-id>/`; Judge reports are normally
at `evaluation/judge/report.json`. Use the printed paths and exact attempt IDs.

`resume SUITE` continues eligible unfinished work. `retry SUITE --agent ID --case N`
targets one unfinished Case (N starts at 1). `reuse SUITE` creates a new linked Suite
with saved Cases. An uncertain accepted request or unsafe replay can remain blocked.
Changing a Profile does not change saved Cases; generate new ones to test the new Profile.

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

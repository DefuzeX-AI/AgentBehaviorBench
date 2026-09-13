# Command-line reference

Run commands from the repository root after installing ABB. `agentbench` loads
`.env` by default; use `--env-file PATH` on commands that support it to select
another dotenv file.

```bash
agentbench --help
agentbench <command> --help
```

## Environment before execution

The current bundled ready Agent runs in Docker. Docker must be installed and
running. Its normal evaluation path also requires:

```dotenv
KUMA_API_KEY=              # DEFUZEX_API_KEY is an accepted alternative
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

`KUMA_API_KEY`/`DEFUZEX_API_KEY` authorizes the default KUMA Case and Judge
SDK. `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` configure model routing for
Docker-based Agents. `TAVILY_API_KEY` is needed by the bundled Company Research
Agent. See the repository [README](../README.md) for setup details.

## `run`

```bash
agentbench run [OPTIONS]
```

Runs every Agent that is both `enabled = true` and `status = "ready"` in the
registry. The command lists the selection and asks for confirmation before
execution; `--yes` accepts up front, and a session with no usable console
declines rather than blocking. Calling `agentbench` with no command is
equivalent to `agentbench run`.

| Option | Meaning |
| --- | --- |
| `--registry PATH` | Registry file; defaults to `resources/registry.toml`. |
| `--sdk NAME` | Evaluation SDK: `kuma`, `panda`, an installed entry-point name, `DISTRIBUTION::NAME`, or `python:MODULE[:OBJECT]`. The default is `kuma`. |
| `--sdk-options PATH` | JSON object passed to the selected SDK. |
| `--sdk-source PATH` | Override the selected SDK's `sdk_source` option; wins over the same key in `--sdk-options`. For `kuma` this is the local SDK checkout, which defaults to a sibling `KUMA-DefuzeX` directory. |
| `--env-file PATH` | Load variables from this dotenv file instead of `.env`. |
| `--output PATH` | Base path for the ABB JSON result snapshot; defaults to `results/result.json`. ABB creates a unique snapshot. |
| `--no-view` | Save the result without starting the browser viewer. |
| `--yes` | Accept the charge and skip the confirmation prompt. |
| `--model MODEL` | Override `OPENROUTER_MODEL` for this run. |
| `--llm-trace terminal` | Print sanitized intercepted model activity. |
| `--llm-trace-max-bytes BYTES` | Legacy streaming spool threshold; payloads are not truncated. |

Examples:

```bash
agentbench run
agentbench run --no-view --output results/nightly.json
agentbench run --model openai/gpt-4.1-mini --llm-trace terminal
agentbench run --sdk kuma --sdk-options sdk-options.json
```

## `evaluate`

```bash
agentbench evaluate [AGENT] [OPTIONS]
```

Evaluates one enabled Agent. Supply its ID or its displayed enabled-Agent
number; omit it to select interactively. The command creates independent SDK
Cases and requires a Judge report to succeed. Creating Cases and calling the
Judge consumes Credits, so it lists the Agent and asks for confirmation first;
pass `--yes` to accept up front.

```bash
agentbench evaluate company-research-agent --cases 1
agentbench evaluate 1 --model openai/gpt-4.1-mini --no-view
agentbench evaluate 1 --yes --no-view             # unattended
```

In addition to the shared `--registry`, `--env-file`, `--model`, `--sdk`,
`--sdk-options`, `--sdk-source`, `--no-view`, and LLM-tracing options,
`evaluate` accepts:

| Option | Meaning |
| --- | --- |
| `--cases N` | Number of independent Cases; defaults to the registry Case count. |
| `--max-steps N` | SDK upper bound on dialogue steps per Case. |
| `--timeout SECONDS` | Override the SDK timeout. |
| `--result-output PATH` | Base path for ABB's result JSON. |
| `--output PATH` | Output option forwarded to the SDK, not ABB's result JSON. |

## `observe`

```bash
agentbench observe [AGENT] [OPTIONS]
```

Runs one enabled Agent with native JSON input and records trace artifacts. It
does **not** create SDK Cases or call a Judge, so it does not require a KUMA or
DefuzeX key. It still needs the Agent's runtime credentials, including
OpenRouter and Tavily for the bundled Company Research Agent.

```bash
agentbench observe --list
agentbench observe company-research-agent --input input.json
agentbench observe company-research-agent --model openai/gpt-4.1-mini
agentbench observe --show results/observe/<run-id>
```

Options: `--agent AGENT` is an alias for the positional selection;
`--input PATH` reads native input JSON; `--output PATH` defaults to
`results/observe`; `--timeout SECONDS` limits execution; `--show PATH` reviews
a saved observe directory offline.

## `certify`

```bash
agentbench certify AGENT_ID [OPTIONS]
```

Runs one registered `adapting` Agent through the certification flow. A
successful run promotes its registry status to `ready`; failed or interrupted
runs retain the existing status. It runs the full benchmark flow and rewrites
the registry, so it asks for confirmation first; pass `--yes` to accept up
front. It supports the same `--registry`, `--sdk`,
`--sdk-options`, `--sdk-source`, `--env-file`, `--output`, `--no-view`,
`--model`, and LLM-tracing options as `run`.

```bash
agentbench certify react-agent --no-view
agentbench certify react-agent --yes --no-view    # unattended
```

## Result and maintenance commands

```bash
# Serve a saved result in the browser viewer.
agentbench view results/benchmark.json [--host HOST] [--port PORT]

# List SDK integrations without importing third-party plugin code.
agentbench sdk list
agentbench sdk show kuma

# Review or archive local result history. Archived history is recoverable.
agentbench clean --dry-run
agentbench clean --yes
```

`clean` only moves data under the default `results/` history into a recoverable
archive. It does not change Agent source, `.env`, registry status, Docker
images, or custom output paths.

# ABB CLI reference

English | [中文](otherLanguages/cli.zh-CN.md) | [Français](otherLanguages/cli.fr.md) | [日本語](otherLanguages/cli.ja.md) | [한국어](otherLanguages/cli.ko.md)

[Back to README](../README.md) · [How to start ABB](Guide.md) · [Agent registry](Registry.md) · [Add an Agent](How%20To%20Add%20Agent.md)

Use this reference for command purposes, every public argument, default behavior, and examples. Install ABB and configure the target Agent before running execution commands.

Replace AGENT_ID, SUITE_ID, CASE_ID, RUN_ID, source paths, and file names with actual values. Agent menu numbers are local to the printed list; Case numbers start at 1. OPTIONS denotes the flags listed in that command’s table. Every command supports -h/--help. Running agentbench without arguments defaults to run.

```bash
agentbench --help
agentbench evaluate --help
agentbench agent add --help
```

agent is a command group with the required subcommand add. sdk requires list or show. Use agentbench agent --help or agentbench sdk --help for group help; groups accept only -h/--help before selecting a subcommand.

## Choose a command

| Command | Purpose and default |
| --- | --- |
| `agentbench run` | Run all enabled Agents whose registry status is ready in one Suite. Use each entry’s case count and step budget. The CLI confirms the selected Agents before execution. |
| `agentbench evaluate` | Generate independent Cases for one enabled Agent, execute it, collect evidence, and obtain Judge results through the selected SDK. Unlike certify, it does not change registry status. |
| `agentbench agent add` | Import a GitHub repository or local directory. With no -b/-c, only import and list source files. -b generates integration configuration; -c runs certification. The two flags can be combined. |
| `agentbench certify` | Execute the registered Case budget of one enabled adapting Agent and promote it to ready when all requested Cases complete without invocation errors. A Judge finding does not by itself prevent promotion; already-ready Agents are not rerun. |
| `agentbench observe` | Execute one native input and save outputs and traces without SDK Case generation or Judge. Currently requires Docker with oneshot execution. --list and --show provide read-only inspection. |
| `agentbench view` | Serve saved results in the local web viewer. Build the web assets first. Open the printed full View URL and keep the command running; Ctrl+C stops it. |
| `agentbench sdk list` | List SDK plugin names found in the SDK directory. This checks discovery, not whether all runtime dependencies are installed. |
| `agentbench sdk show` | Load one SDK plugin and show its source, execution mode, and whether it allows implicit selection. |
| `agentbench resume` | Continue eligible unfinished work from a saved Suite using its saved Cases and configuration plus current credentials. Does not generate new Cases or deliberately rerun completed ones. |
| `agentbench retry` | Recover one unfinished Case in its original Suite using the original inputs. Depending on its saved state, recover the request or replay from the first input. Replay eligibility still applies. |
| `agentbench reuse` | Reuse saved Case inputs for fresh Agent execution, evidence collection, and judging in a linked reuse Suite. Keeps original results and does not generate new inputs. Use this to rerun a completed Case. |
| `agentbench clean` | Archive unreferenced top-level history from the project results directory into cache/history-trash. Preserve saved Suites and referenced artifacts. Preview first; stop runs and viewers before actual cleanup. |

## `run`

Run all enabled Agents whose registry status is ready in one Suite. Use each entry’s case count and step budget. The CLI confirms the selected Agents before execution.

```text
agentbench run [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `--sdk NAME` | Choose an SDK directory name from sdk list. Bundled default: kuma; local requires explicit selection. If several plugins permit implicit selection, specify a name. | `--sdk kuma` |
| `--sdk-options PATH` | Read a JSON object of options accepted by the selected SDK. Default: no explicit options; the SDK supplies defaults. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Maximum extra automatic attempts for safely recoverable Case failures. Nonnegative integer; default 2. Zero disables automatic retries. | `--case-retries 0` |
| `--retry-delay SECONDS` | Initial retry backoff, in seconds. Finite nonnegative number; default 5. Later delays increase within the retry policy. | `--retry-delay 5` |
| `-y, --yes` | Skip the execution confirmation prompt. Default: ask for confirmation. | `--yes` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--results-dir DIR` | ABB result root, created if missing. Default when running from the checkout root: results/. Events are saved at DIR/suites/SUITE_ID/events.json. Mutually exclusive with the legacy result-location option. | `--results-dir results/my-run` |
| `--output PATH` | Deprecated ABB result location. A file path selects its parent; the named file is not created. Prefer --results-dir. Default result root: project results/ when running from the checkout root. | `--output results/legacy.json` |
| `--no-view` | Save results without starting the web viewer. Default: start or reuse the viewer; built web assets are needed. | `--no-view` |
| `--model MODEL` | Override ABB’s replacement target model. Default: the selected provider’s configuration. Native ACP models follow their Agent configuration. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | Legacy streaming memory-spool threshold, in bytes; default 262144 (256 KiB). It does not truncate stored payloads. | `--llm-trace-max-bytes 262144` |

run has no --registry, --cases, or --max-steps options. Change per-Agent defaults in the registry; SDK JSON max_steps can override the step budget.

### Examples

```bash
agentbench run --sdk kuma
agentbench run --sdk local --yes --no-view --results-dir results/smoke
```

## `evaluate`

Generate independent Cases for one enabled Agent, execute it, collect evidence, and obtain Judge results through the selected SDK. Unlike certify, it does not change registry status.

```text
agentbench evaluate [AGENT] [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `-y, --yes` | Skip the execution confirmation prompt. Default: ask for confirmation. | `--yes` |
| `AGENT` | Optional enabled Agent ID or menu number. Omit for interactive selection; with --yes, specify an Agent. Does not require status ready. | `react-agent` |
| `--registry PATH` | Choose the Agent registry. Default: project resources/registry.toml. | `--registry resources/registry.toml` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--model MODEL` | Override ABB’s replacement target model. Default: the selected provider’s configuration. Native ACP models follow their Agent configuration. | `--model openai/gpt-4.1-mini` |
| `--sdk NAME` | Choose an SDK directory name from sdk list. Bundled default: kuma; local requires explicit selection. If several plugins permit implicit selection, specify a name. | `--sdk kuma` |
| `--sdk-options PATH` | Read a JSON object of options accepted by the selected SDK. Default: no explicit options; the SDK supplies defaults. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Maximum extra automatic attempts for safely recoverable Case failures. Nonnegative integer; default 2. Zero disables automatic retries. | `--case-retries 0` |
| `--retry-delay SECONDS` | Initial retry backoff, in seconds. Finite nonnegative number; default 5. Later delays increase within the retry policy. | `--retry-delay 5` |
| `--no-view` | Save results without starting the web viewer. Default: start or reuse the viewer; built web assets are needed. | `--no-view` |
| `--llm-trace-max-bytes BYTES` | Legacy streaming memory-spool threshold, in bytes; default 262144 (256 KiB). It does not truncate stored payloads. | `--llm-trace-max-bytes 262144` |
| `--results-dir DIR` | ABB result root, created if missing. Default when running from the checkout root: results/. Events are saved at DIR/suites/SUITE_ID/events.json. Mutually exclusive with the legacy result-location option. | `--results-dir results/my-run` |
| `--result-output PATH` | Deprecated ABB result location; a file path selects its parent without creating that file. Prefer --results-dir. Mutually exclusive with --results-dir; default: project results/. | `--result-output results/legacy.json` |
| `--output DIR` | SDK artifact directory, separate from ABB Suite results. Overrides SDK JSON output. KUMA/local default: results/observe. | `--output results/sdk-artifacts` |
| `--timeout SECONDS` | Positive finite SDK execution timeout, in seconds. Overrides SDK JSON timeout. KUMA/local default: 2400; other SDKs define their own. | `--timeout 2400` |
| `--cases N` | Positive number of independent Cases. Default: this Agent’s registry case value. Overrides it for this run without editing the registry. | `--cases 1` |
| `--max-steps N` | Positive SDK dialogue-step limit per Case. Overrides registry step and SDK JSON max_steps; otherwise use those defaults. Some Agents support one step only. | `--max-steps 3` |

### Examples

```bash
agentbench evaluate react-agent --sdk kuma --cases 1
agentbench evaluate react-agent --sdk local --cases 1 --yes --no-view --results-dir results/smoke
agentbench evaluate react-agent --sdk kuma --cases 2 --max-steps 3 --output results/sdk-artifacts --results-dir results/my-run --no-view
```

## `agent add`

Import a GitHub repository or local directory. With no -b/-c, only import and list source files. -b generates integration configuration; -c runs certification. The two flags can be combined.

```text
agentbench agent add SOURCE [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `SOURCE` | Required HTTPS GitHub repository URL or absolute local directory. Branch/file URLs are not accepted. Plain import creates a unit; -b/-c can reuse a matching imported source. | `https://github.com/langchain-ai/react-agent` |
| `--agents-dir DIR` | Parent directory for numbered Agent units. Default: resources/agents beside the selected project’s default registry. Generated units must be inside the root of --registry. | `--agents-dir resources/agents` |
| `-b, --build` | Generate, validate, and save integration configuration, then register adapting. Reuses valid completed files. Supports LangGraph and ACP; does not build Docker. Default: off. | `-b` |
| `-c, --certify` | Validate generated or manually prepared integration, register it, then run certification. Does not imply -b. Default: off. | `-c` |
| `--registry PATH` | Choose the Agent registry. Default: project resources/registry.toml. | `--registry resources/registry.toml` |
| `--build-settings PATH` | TOML file with a [build] table overriding generation budgets/model. Default: packaged settings. Used with -b. | `--build-settings build-settings.toml` |
| `--build-model MODEL` | OpenRouter model for -b configuration generation. Priority: this flag, [build].model, OPENROUTER_BUILD_MODEL, OPENROUTER_MODEL. Needs structured-output support. | `--build-model openai/gpt-4.1-mini` |
| `--answers PATH` | UTF-8 text answers to questions from a previous generation plan; repeat the -b command with this file. Default: no answers file. | `--answers answers.txt` |
| `--with-observe` | With -b, generate interactive observe input fields. Default: off. Rejected without -b. | `--with-observe` |
| `--agent-timeout SECONDS` | With -b, set the generated Agent runtime timeout. Positive finite seconds; default 300. Does not set the generation request timeout. | `--agent-timeout 600` |
| `--adapter-context PATH` | With -b, load an explicit deployment-context JSON object, at most 64 KiB. Default: no context override. Contents must match the Agent’s integration. | `--adapter-context adapter-context.json` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--model MODEL` | Replacement target model for -c certification, independent of --build-model. Default: provider configuration; native ACP model selection follows the Agent. | `--model openai/gpt-4.1-mini` |
| `--output PATH` | Certification result location used with -c. For managed Suites, a file path selects its parent without creating the named file. Default: project results/. This command has no --results-dir flag. | `--output results/add-certification.json` |
| `--no-view` | With -c, save certification results without starting the viewer. Does not affect source import or configuration generation. Default: viewer enabled for certification. | `--no-view` |
| `-y, --yes` | Skip the -c certification confirmation. Default: prompt. Does not answer planning questions. | `--yes` |
| `--sdk NAME` | Choose an SDK directory name from sdk list. Bundled default: kuma; local requires explicit selection. If several plugins permit implicit selection, specify a name. | `--sdk kuma` |
| `--sdk-options PATH` | Read a JSON object of SDK options for -c certification only, not -b generation. Default: the SDK supplies defaults. | `--sdk-options sdk-options.json` |

Use an absolute local path. On Windows, SOURCE can be "C:\work\local-agent". -d is rejected. Configuration generation currently uses OpenRouter and requires an SDK with onboarding hooks; bundled local does not provide them.

### Examples

```bash
agentbench agent add https://github.com/langchain-ai/react-agent
agentbench agent add /absolute/path/to/local-agent -b --sdk kuma --build-model openai/gpt-4.1-mini
agentbench agent add /absolute/path/to/local-agent -b -c --sdk kuma --no-view
```

## `certify`

Execute the registered Case budget of one enabled adapting Agent and promote it to ready when all requested Cases complete without invocation errors. A Judge finding does not by itself prevent promotion; already-ready Agents are not rerun.

```text
agentbench certify AGENT_ID [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `-y, --yes` | Skip the execution confirmation prompt. Default: ask for confirmation. | `--yes` |
| `--registry PATH` | Choose the Agent registry. Default: project resources/registry.toml. | `--registry resources/registry.toml` |
| `--sdk NAME` | Choose an SDK directory name from sdk list. Bundled default: kuma; local requires explicit selection. If several plugins permit implicit selection, specify a name. | `--sdk kuma` |
| `--sdk-options PATH` | Read a JSON object of options accepted by the selected SDK. Default: no explicit options; the SDK supplies defaults. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Maximum extra automatic attempts for safely recoverable Case failures. Nonnegative integer; default 2. Zero disables automatic retries. | `--case-retries 0` |
| `--retry-delay SECONDS` | Initial retry backoff, in seconds. Finite nonnegative number; default 5. Later delays increase within the retry policy. | `--retry-delay 5` |
| `--no-view` | Save results without starting the web viewer. Default: start or reuse the viewer; built web assets are needed. | `--no-view` |
| `AGENT_ID` | Required exact ID of an enabled registered Agent. Certifies adapting Agents; ready Agents return without a new run. | `folder-mover-agent` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--results-dir DIR` | ABB result root, created if missing. Default when running from the checkout root: results/. Events are saved at DIR/suites/SUITE_ID/events.json. Mutually exclusive with the legacy result-location option. | `--results-dir results/my-run` |
| `--output PATH` | Deprecated ABB result location. A file path selects its parent; the named file is not created. Prefer --results-dir. Default result root: project results/ when running from the checkout root. | `--output results/legacy.json` |
| `--model MODEL` | Override ABB’s replacement target model. Default: the selected provider’s configuration. Native ACP models follow their Agent configuration. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | Legacy streaming memory-spool threshold, in bytes; default 262144 (256 KiB). It does not truncate stored payloads. | `--llm-trace-max-bytes 262144` |

### Examples

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
agentbench certify AGENT_ID --sdk local --yes --no-view --results-dir results/certification
```

## `observe`

Execute one native input and save outputs and traces without SDK Case generation or Judge. Currently requires Docker with oneshot execution. --list and --show provide read-only inspection.

```text
agentbench observe [AGENT] [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `AGENT` | Optional enabled Agent ID or menu number; omit for interactive selection. Mutually exclusive with --agent. | `react-agent` |
| `--agent AGENT` | Alternative to the positional Agent ID or menu number; do not specify both. | `--agent react-agent` |
| `--registry PATH` | Choose the Agent registry. Default: project resources/registry.toml. | `--registry resources/registry.toml` |
| `--list` | List enabled Agents and exit without executing one. Default: off. | `--list` |
| `--input PATH` | Read one native input from UTF-8 JSON. A text input is a JSON string, including quotes. Default: prompt using observe fields or raw JSON. | `--input native-input.json` |
| `--output DIR` | Observe artifact root; a new run-ID subdirectory is created. Default: results/observe. | `--output results/observe` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--model MODEL` | Override ABB’s replacement target model. Default: the selected provider’s configuration. Native ACP models follow their Agent configuration. | `--model openai/gpt-4.1-mini` |
| `--timeout SECONDS` | Override Agent execution timeout with positive finite seconds. Default: the Agent’s runtime configuration. | `--timeout 300` |
| `--show DIR` | Review a saved observe run offline and exit. Does not execute the Agent or use the other execution options. | `--show results/observe/RUN_ID` |

### Examples

```bash
agentbench observe --list
agentbench observe react-agent --input native-input.json --output results/observe --timeout 300
agentbench observe --show results/observe/RUN_ID
```

## `view`

Serve saved results in the local web viewer. Build the web assets first. Open the printed full View URL and keep the command running; Ctrl+C stops it.

```text
agentbench view RESULT_LOG [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `RESULT_LOG` | Required existing JSON result file, normally events.json from Result saved. Pass the file, not its directory. | `results/suites/SUITE_ID/events.json` |
| `--host ADDRESS` | Viewer listening address. Default: 127.0.0.1. | `--host 127.0.0.1` |
| `--port N` | Listening port, 0–65535; default 8765. Zero requests an automatically assigned port. The default viewer can choose another port when occupied. | `--port 0` |

### Examples

```bash
agentbench view results/suites/SUITE_ID/events.json
agentbench view results/suites/SUITE_ID/events.json --host 127.0.0.1 --port 0
```

## `sdk list`

List SDK plugin names found in the SDK directory. This checks discovery, not whether all runtime dependencies are installed.

```text
agentbench sdk list [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |

### Examples

```bash
agentbench sdk list
```

## `sdk show`

Load one SDK plugin and show its source, execution mode, and whether it allows implicit selection.

```text
agentbench sdk show NAME [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `NAME` | Required SDK directory name, matched case-insensitively; use a name from sdk list. | `kuma` |

### Examples

```bash
agentbench sdk show kuma
agentbench sdk show local
```

## `resume`

Continue eligible unfinished work from a saved Suite using its saved Cases and configuration plus current credentials. Does not generate new Cases or deliberately rerun completed ones.

```text
agentbench resume SUITE [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `SUITE` | Required saved Suite ID, directory, or events.json path. An ID is resolved under --suite-root. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Directory containing Suite-ID directories. Default: results/suites under the current working directory. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |

### Examples

```bash
agentbench resume results/suites/SUITE_ID
agentbench resume SUITE_ID --suite-root results/my-run/suites --env-file .env.testing
```

## `retry`

Recover one unfinished Case in its original Suite using the original inputs. Depending on its saved state, recover the request or replay from the first input. Replay eligibility still applies.

```text
agentbench retry SUITE --agent ID --case N [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `SUITE` | Required saved Suite ID, directory, or events.json path. An ID is resolved under --suite-root. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Directory containing Suite-ID directories. Default: results/suites under the current working directory. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--agent ID` | Required exact Agent ID from the original Suite; not a menu number. | `--agent react-agent` |
| `--case N` | Required one-based Case number, a positive integer. Targets that Case of --agent. | `--case 1` |

### Examples

```bash
agentbench retry results/suites/SUITE_ID --agent react-agent --case 1
```

## `reuse`

Reuse saved Case inputs for fresh Agent execution, evidence collection, and judging in a linked reuse Suite. Keeps original results and does not generate new inputs. Use this to rerun a completed Case.

```text
agentbench reuse SOURCE [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `SOURCE` | Required saved Suite ID/path, Case ID, artifact run ID, case.json or attempt path. A Suite selects all Cases unless --agent and --case are supplied. Ambiguous IDs require an explicit source. | `CASE_ID` |
| `--suite-root DIR` | Restrict saved-Suite lookup to this directory. Default: project results plus indexed external Suites. | `--suite-root results/my-run/suites` |
| `--agent ID` | With a Suite source, select an exact Agent ID. Must be paired with --case. Omit both to reuse all Cases. | `--agent react-agent` |
| `--case N` | Positive one-based Case number in a Suite; must be paired with --agent. Not used with a direct Case ID. | `--case 2` |
| `--output-root DIR` | Parent directory for reuse Suites. New Suites are saved at DIR/SUITE_ID; default: source Suite’s parent. Only join compatible active reuse Suites directly under this directory. | `--output-root results/reruns` |
| `--env-file PATH` | Load another environment file. Default: project .env. Exported shell variables take precedence. | `--env-file .env.testing` |
| `--model MODEL` | Replacement target model for the new evaluation. Default: saved model settings; native ACP model selection follows the Agent configuration. | `--model openai/gpt-4.1-mini` |
| `--max-steps N` | Positive SDK dialogue-step budget for the new evaluation; default: saved runner settings. Does not generate additional inputs in the saved Case. | `--max-steps 3` |

Compatible requests may join an active reuse Suite. Each intentional request adds a fresh execution. This command has no --no-view, --yes, --sdk, or --cases flags; it prints a saved-result/viewer link.

### Examples

```bash
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent react-agent --case 2
agentbench reuse results/suites/SUITE_ID --output-root results/reruns --max-steps 3
```

## `clean`

Archive unreferenced top-level history from the project results directory into cache/history-trash. Preserve saved Suites and referenced artifacts. Preview first; stop runs and viewers before actual cleanup.

```text
agentbench clean [OPTIONS]
```

| Argument | Purpose and default | Example |
| --- | --- | --- |
| `-h, --help` | Show help for this command and exit. | `--help` |
| `--dry-run` | List archival candidates without moving files. Default: off. | `--dry-run` |
| `-y, --yes` | Skip the archival confirmation prompt. Default: ask. Stop active runs and viewers before actual cleanup. | `--yes` |

### Examples

```bash
agentbench clean --dry-run
agentbench clean
```

## Files used in examples

Create these files before using the corresponding arguments. JSON files must contain valid JSON; sdk-options.json must be an object. The shown SDK options are supported by kuma/local; another plugin may accept different keys.

`sdk-options.json`:

```json
{
  "timeout": 2400,
  "max_steps": 3
}
```

`build-settings.toml`:

```toml
[build]
model = "openai/gpt-4.1-mini"
timeout_seconds = 120
```

`native-input.json`:

```json
"Describe your capabilities and limitations."
```

native-input.json must match the Agent’s native input schema. answers.txt contains factual answers to the planner’s questions. adapter-context.json is a deployment-context object supplied with -b; its fields depend on the Agent, so there is no universal object to copy.

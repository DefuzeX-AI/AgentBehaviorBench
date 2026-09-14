# CLI reference

Run `agentbench --help` and `agentbench COMMAND --help` for the installed version.
Run commands from the repository root, with your virtual environment activated.

| Command | Selection and outcome |
| --- | --- |
| `run` | All enabled `ready` registrations. Uses each registry `case` count. |
| `evaluate AGENT_ID --cases N` | One enabled Agent, including `adapting`. Every Case has its own Run. |
| `certify AGENT_ID` | Executes certification using the registry Case count before updating status to `ready`. Judge findings are allowed; execution failures are not. |
| `observe AGENT_ID` | Native Agent input and trace, without Case generation or Judge. |
| `view PATH` | Reopens a saved result JSON; `--port 0` selects a free local port. |
| `resume SUITE` | Continues unfinished slots in a persisted Suite; retains completed Judge findings. |
| `retry SUITE --agent ID --case N` | Requests recovery of one unfinished Case, with a one-based Case number. |
| `reuse SUITE` | Evaluates all saved Cases in a linked new Suite under the current code/configuration. |
| `sdk list` | Lists plugin directories, without importing implementations. |
| `clean --dry-run` | Previews recoverable result archival. |

For `run`, `evaluate` and `certify`, `--yes` accepts the initial confirmation.
`--no-view` suppresses the viewer, but does not accept confirmation. Use both in
automation. `evaluate --yes` requires an explicit Agent selection.

```bash
agentbench evaluate react-agent --cases 4 --max-steps 3 --yes --no-view \
  --result-output results/react.json
agentbench run --yes --no-view --output results/suite.json
```

The saved filename includes a unique suite identity; use the path printed by the
command. `--cases 4` means four independent scenarios. `--max-steps 3` is the
upper bound on Inputs in each Case, not the number of internal tool/model calls.
The Case can finish earlier. `ABB_MAX_PARALLEL_CASES=4` controls the shared Case
worker pool; Inputs inside one Case stay sequential.

| Option | Meaning |
| --- | --- |
| `--registry PATH` | Alternate registry TOML. |
| `--env-file PATH` | Alternate dotenv file; exported variables take precedence. |
| `--model MODEL` | Overrides `OPENROUTER_MODEL` for this invocation. |
| `--sdk NAME` | Selects a discovered SDK plugin. |
| `--sdk-options PATH` | JSON object passed to the plugin. |
| `--result-output PATH` | ABB result naming base for evaluate/certify. |
| `--output PATH` | SDK output override for evaluate/certify; ABB result naming base for run. |
| `--timeout SECONDS` | SDK execution deadline for evaluate/certify. |
| `--llm-trace-max-bytes N` | In-memory trace spool threshold, not a truncation allowance. |
| `--case-retries N` | Maximum automatic retries of a safe transient Case failure; default 2, 0 disables. Available on run/evaluate/certify. |
| `--retry-delay SECONDS` | Initial backoff before an automatic retry; remaining delay and budget survive resume. |

Example Kuma options (see the [SDK adapter guide](SDK-Directory-Adapters.md)):

```json
{"sdk_request_options": {"timeout": 300, "operation_wait_timeout": 600, "max_retries": 2}}
```

`evaluate` exits 0 when execution succeeds and all Judge reports pass; a Judge
finding returns 1. Infrastructure errors remain failures. Invalid CLI configuration
normally returns a nonzero code (parser errors return 2; evaluate setup failures
can return 1). Declining confirmation cancels without starting execution and returns 0.
Inspect the result's individual Cases to distinguish findings from run failures.

Saved directory-SDK Suites contain `plan.json`, `events.json`, and immutable Case
files. Resume/retry accept the Suite directory, its events file, or a Suite ID
under `results/suites`; use `--suite-root` for an alternate parent directory.
Credentials are loaded fresh with `--env-file` and are not saved in the plan.
Code, model, or dependency changes require a linked new Suite through `reuse`.
See [reuse commands](Case-Reuse-Commands.md) and
[recovery implementation](Suite-Recovery-Implementation.md) for restrictions.

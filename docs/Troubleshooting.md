# Results and troubleshooting

[Setup](../README.md) · [Agent onboarding](How%20To%20Add%20Agent.md) ·
[中文指南](otherLanguages/Guide.zh-CN.md)

## Check the failing stage

| Symptom | Check / next action |
| --- | --- |
| `agentbench` missing or importing an old checkout | Activate this checkout's `.venv`, check `python -m pip --version`, then `python -m pip install -e .`. From the root, `python -m agentbench --help` also checks local imports. |
| IDE cannot resolve `kuma…` | Install the plugin's `requirements.txt` in the host venv and select that interpreter. Docker's packages are separate. |
| `Trace UI not built or incomplete` | Use compatible Node (20.19+ on 20.x or 22.12+), then `cd web`, `npm ci`, `npm run build`. Open the actual saved result path. |
| Wrong Suite / URL | Use the complete printed `View:` URL including Suite ID and port. Python selects a free port if 8765 is occupied. |
| Newly printed Suite URL returns 404 on Windows | Update ABB and open the saved `events.json` with `agentbench view`. Older viewers could share an occupied port and send requests to a previous Suite. Restarting the viewer loads the fix; the benchmark can continue running. |
| Docker unavailable / permission denied | Run `docker info` as the same user. Start Desktop/Engine and inspect Docker context/permissions. Do not run ABB as root to hide ownership problems. |
| Interceptor startup reports `bind source path does not exist` on macOS / Colima | Update ABB to use the home-directory default. For custom VM shares, set `ABB_DOCKER_TMPDIR` to a writable absolute path shared with Docker. See [Docker-mounted temporary files](#docker-mounted-temporary-files). |
| Python 3.10 Case generation reports missing `tomllib` / `tomli` | Update ABB and rebuild the evaluation image. Worker staging installs `tomli` for Python below 3.11 into the image's selected Python environment; installing it only on the host does not repair an existing image. See [#85](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/85). |
| Every Docker Case fails in Case generation with `ModuleNotFoundError: No module named 'filelock'` | Update ABB and rebuild the evaluation image. Worker staging installs `filelock` into the image's selected Python environment because the injected Suite lock imports it; installing it only on the host does not repair an existing image. See [#391](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/391). |
| Missing/invalid KUMA key | Nonempty `KUMA_API_KEY` takes precedence over `DEFUZEX_API_KEY`. Check exported variables overriding `.env` and service account access without displaying keys. |
| Missing model / quota / provider error | `OPENROUTER_MODEL` has no runtime default. Check the slug, account access, funds/limits and tool/protocol support. A key is not a model name. |
| `agent add -b` rejects model response | See [Structured-output generation failures](#structured-output-generation-failures). Inspect field/JSON diagnostics, correction exhaustion and provider finish metadata. |
| Tool authentication error | The Agent must declare its required keys and the CLI environment must provide them. `.env` is not mounted wholesale. |
| Blocked route / trace rejection | Inspect the recorded host/path/protocol and declared routes. Fix source-backed route mismatches; do not disable observation or permit arbitrary traffic to obtain pass. |
| No ready Agents | Inspect `agentbench observe --list` and the registry. `run` selects enabled ready registrations; certify adapting integrations after dependencies work. |
| Judge `model_invalid_result` | Inspect SDK/report artifacts. Separate remote Judge output validation from the tested Agent's answer. |
| Blocked recovery | Preserve plan, request ledger and artifacts. Unconfirmed accepted requests, unsafe replay, permissions or incomplete cleanup may block retries. Do not duplicate paid requests blindly. |

`OPENROUTER_BASE_URL` changes the model upstream; optional `OPENROUTER_HTTP_REFERER`
and `OPENROUTER_APP_TITLE` identify requests. They do not change KUMA's endpoint.
The onboarding catalog reads `KUMA_BASE_URL`, but evaluation does not forward it
end to end and allows the default DefuzeX backend. Do not treat it as a working
evaluation override: see [#52](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/52).

## Docker-mounted temporary files

On macOS, ABB creates each model interceptor's configuration, credentials and CA
export in a private temporary directory under `~/.cache/agentbench/docker/`.
[Colima shares the home directory by default](https://colima.run/docs/faq/#docker-bind-mount-showing-empty),
while the macOS system temporary
path under `/private/var/...` is not shared by default. This addresses
[#116](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/116) without requiring
a global `TMPDIR` workaround. Other platforms retain Python's default temporary
location unless an override is configured.

For custom Docker VM shares, set an absolute host directory that the Docker daemon
can access at the same path, for example:

```bash
export ABB_DOCKER_TMPDIR="$HOME/abb-docker-tmp"
```

ABB creates this parent if needed. The override takes precedence on every platform;
macOS otherwise uses the home-directory default even if `TMPDIR` is set. Ensure the
chosen location (including any resolved symlink target) is included in your VM's
file-sharing configuration. A remote daemon also needs access to the actual host
files; setting this variable alone does not copy them to another machine.

Each interceptor receives a unique directory with owner-only permissions. Its files
are removed on normal shutdown and startup failure; the reusable parent remains.
These files can contain credentials, so use a local private location outside
published result artifacts. A forcibly killed host process may leave a directory
behind; remove such leftovers only after confirming its interceptor has stopped.

## Structured-output generation failures

Configuration generation with `agent add -b` validates model replies against each
stage's full local schema. The diagnostic and correction paths address
[#112](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/112).
Fenced/prose JSON tolerance ([#89](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/89))
is separate: such content must be corrected by the model rather than silently extracted.

| Error | Current behavior | What to inspect |
| --- | --- | --- |
| `Model response schema mismatch` | Bounded diagnostics include field paths, expected constraints and actual types; corrections receive those diagnostics and the previous parsed response. | `response-N.json` and `validation-N.json`; planning uses `plan-` prefixes, review uses `review-N.json` and `review-validation-N.json`. |
| `OpenRouter model content is invalid JSON` / `must be a JSON object` | Corrects the same stage using safe previous content and decoder line/column/offset or the actual root type. Malformed content is not saved. | Validation records hold safe diagnostics. The raw model content is kept only in memory for the correction request after credential checks. |
| `OpenRouter returned an invalid structured response envelope` | Invalid provider envelope or missing content stops without content corrections. | Check the provider configuration; this is distinct from JSON errors inside model content. |
| `OpenRouter did not finish the configuration` | A finish reason other than `stop` stops without content corrections. | `provider-N.json` and terminal `build-result.json` diagnostics include available finish reason, usage (including reasoning tokens) and content length. Confirm `length` before increasing output budgets. |

Metadata records contain only selected finish reasons and numeric usage/length fields,
not raw provider responses. A credential-bearing response is never saved or sent back.
A review-format failure retries the review of the same candidate; actual compatibility
issues can still require regenerating the file.

1. Use the attempt path printed by the failed build. Preserve `build-result.json`,
   `plan-response-N.json` / `plan-validation-N.json` when present, and the failing
   file's `steps/<number>-<filename>/` directory. `current_file` identifies a file
   stage when available; planning can fail before that field is set. Keep valid
   completed integration files and the checkpoint for reuse.
2. Inspect saved parsed responses locally against the **full local schema**, not
   the reduced schema sent to the provider. File content uses
   `agentbench/onboarding/build_agent_env/openrouter_provider/assets/file-response.schema.json`;
   LangGraph `agent.toml` facts use
   `agentbench/onboarding/build_agent_env/frameworks/langgraph/assets/manifest/analysis.schema.json`.
   Planning and review have their own schemas. For example, `status` must be
   `complete`, `needs_input` or `unsupported`, and a file response must include
   `path`. Current LangGraph `adapter.config` and `adapter.graph_id` allow `null`
   for a native factory binding; #112's older null-field failure is not the current
   contract. Do not invent a graph descriptor to satisfy that historical example.
3. Supply genuine missing deployment information with `--answers answers.txt`.
   A schema or JSON decode failure is not itself a `needs_input` request. For
   provider incompatibility, choose a model that supports strict structured output
   using `--build-model MODEL`, then repeat the add command for the same source.
   Reusable files are preserved; a model change invalidates planning/review caches
   and can trigger additional paid requests. Editing a saved `response-N.json`
   does not feed a correction into the next build.
4. Do not increase retry budgets without identifying a change that could resolve
   the failure. The packaged `repair_attempts = 1` permits one additional correction
   per planning stage or file, shared across model-content JSON decoding, schema
   checks, file validation and review. `retries` handles transient transport/HTTP
   failures separately. To limit correction
   calls while investigating, create `build-settings.toml` containing:

   ```toml
   [build]
   repair_attempts = 0
   ```

   Then run:

   ```bash
   agentbench agent add https://github.com/owner/repository -b --sdk kuma --build-settings build-settings.toml
   ```

   This disables correction attempts, not initial generation, reviews, source
   follow-ups or transport retries. It is a cost-control option, not a fix.

When reporting a failure, include the checkout commit, generation model, stage,
settings and a sanitized structural description such as `$.status: invalid enum`
or `$.path: missing required property`. Inspect source and model responses locally;
exclude credentials and confidential generated content from shared diagnostics.

## Interpret results on two axes

| Execution | Judge | Meaning |
| --- | --- | --- |
| Completed and host accepted | `pass` | Met this Case's criteria. |
| Completed and host accepted | `issue` | Behavioral finding; read the issue and steps. |
| Completed and host accepted | `insufficient_evidence` | Required behavior could not be established; not a proven defect by itself. |
| Blocked / host rejected | May retain a report | Execution/evidence acceptance failed; receiving a report does not make it accepted. |
| Running / retry wait | Pending | Keep partial results and attempt history. |

`BenchmarkResult.passed` requires report status `pass`; aggregate `FAILED` therefore
includes completed issue/insufficient-evidence Cases. `evaluate`/`run` can exit
nonzero for a delivered non-pass verdict. Certification checks completeness and
can promote an Agent with findings. Report both execution state and Judge verdict.

A real tool call, a simulated example and “I uploaded the file” are different
evidence. Check actual traffic before claiming an upload or state change. For a
`partial` trace, inspect its reason: filtering attributes, missing spans and failed
export are not equivalent.

## Find the supporting artifacts

Use printed paths. For managed KUMA Suites:

- `results/suites/<suite-id>/`: plan, immutable Cases and `events.json`.
- `results/observe/<artifact-run-id>/run.json`: execution metadata/failure status.
- `network.jsonl`: recorded model and tool traffic for that attempt.
- `evaluation/case.json`: selected Case. `evaluation/inputs/<step>/`: input, result,
  submitted output, evidence and capture/OTel status when those stages completed.
- `evaluation/judge/report.json`: Judge result when available.

Use the Case/attempt's artifact ID, not just the Agent name. Failure before a stage
starts may leave its files absent. `observe --show RUN_DIRECTORY` reviews native
observation artifacts offline; `view` opens a result JSON using the built web UI.

## Runs without model calls

An Agent may return a cached answer, reject an input, use only tools, or perform
deterministic work without calling a model. Zero intercepted model calls does not
reject the run; the Judge evaluates the actual output and available evidence.
Host trace validation still checks observed calls for terminal outcomes, capture
errors, truncation and persistence failures. Zero calls alone does not prove that
all possible model traffic was observed.

The former `[llm_interception].required` flag is no longer used. Remove it from
Agent manifests; older manifests containing either value are still accepted, but
the flag neither requires a model call nor disables trace validation. A tool
route's separate `required` field still controls required network operations.

## Share a report

**Export current report** downloads JSON containing all current Cases and attempt
histories, excluding control capabilities. It does not bundle referenced traces.
Review prompts, outputs and tool data before sharing; removing control tokens is
not a general privacy guarantee.

For full reproduction preserve Suite and referenced attempt directories, plus
source/config revisions. Saved paths may be absolute; there is no guaranteed
portable import/archive command. `web/dist/index.html` depends on JS/CSS and local
APIs; it is not a standalone report. A separately created HTML is standalone only
if its required data/assets are embedded; check that particular file.

## Resume, retry, reuse and clean

- `resume SUITE`: continue eligible unfinished slots with saved Cases/request state.
- `retry SUITE --agent ID --case N`: target an unfinished Case; N starts at 1.
- `reuse SUITE`: new linked Suite using saved Cases and current code. Changing a
  Profile does not change saved Cases; use fresh generation to test the new Profile.
- Completed findings are retained, not automatically rerun until they pass.

Start with `agentbench clean --dry-run`. Saved Suites and referenced artifacts are
protected; unreferenced top-level history moves to `cache/history-trash/<batch>/`.
Stop runs/viewers before confirming. Agent source, `.env`, registry, images and
custom output paths are untouched. To restore, stop runs and move archived files
back without overwriting newer results. This is history archiving, not a universal
cache reset.


## Generation, native aborts and dependency waits

`dictionary changed size during iteration` in `TraceCallback.on_chain_end` can
come from a parallel graph extending shared state while the observer serializes
it. Current observation code snapshots dictionary entries before recursively
converting values. Run with the current ABB container build; this historical
observer failure is not evidence of an Agent defect.

`Agent response exceeds transport byte limit` concerns the whole per-Input
response directory, including framework traces and OTel payloads. It does not
refer only to the final answer or to an API token quota. The default is 1 GiB;
set `ABB_AGENT_RESPONSE_MAX_BYTES` to a positive byte count in the host environment
or `.env` if a different budget is needed. `ABB_AGENT_RESPONSE_MAX_FILES` defaults
to 20,000. Effective limits are saved in `request/evaluation.json`. Copies remain
streamed, bounded and checked for links/special files. An over-limit response
fails explicitly; partial copies must not be treated as complete evidence.

Case generation makes at most five total attempts per rejected candidate slot.
Successfully saved Cases keep their original indices. Each attempt is recorded in
`case-collection.json`; after the fifth failure the remaining slots for that Agent
are left unattempted and its generation container is closed. Other Agents continue.
Invalid credentials and ambiguous remote acceptance do not trigger five blind
requests: inspect the saved SDK request identity before attempting recovery.

An ACP peer returning `stopReason=cancelled` is an Agent abort, distinct from a
host cancellation request. ACP closes failed sessions, so ABB stops delivering
later Inputs to them. The original Case remains intact; `termination.json` and
`manifest.json` name the committed prefix and unexecuted tail. Judge receives the
original committed evidence. A missing tool completion at the prompt boundary is
recorded as `not_observed`, never as a successful tool result. Receiving a Judge
report does not turn a native failure into a passing execution.

Recognized native dependency errors pause subsequent Case dispatch for the affected
Agent. The coordinator releases execution slots, tries other Agents, and returns
the waiting Agent to the ready queue after `Retry-After` or bounded backoff. If the
exception names a dependency host, other unfinished Agents declaring that host
share the cooldown; this is conservative host grouping, not per-credential rate
limiting. Cooldown timestamps and budgets survive Suite resume. Existing in-flight
Cases finish normally. A generic step-budget timeout alone does not prove an
upstream outage.

Quota exhaustion or invalid credentials block dependent pending work until an
explicit recovery after configuration is repaired. Automatic cooldown is bounded
by the Suite retry policy; waits over one hour require explicit recovery. Completed
reports are retained. Failed Cases are replayed only when their existing recovery
contract explicitly permits isolated replay. This mechanism schedules whole Cases;
it does not checkpoint arbitrary Agent memory or resume a failed turn in place.
LangGraph's current Case retains its existing continue-on-failure policy.

Docker address-pool exhaustion before container startup is separately classified.
Generation preparation waits and retries up to five total attempts; execution
startup uses the normal bounded Case retry budget because no Agent has run yet.
Only this attempt's owned resources are cleaned up. ABB does not prune unrelated
networks or change Docker's global address pools. Build downloads, unknown Docker
client interruptions and missing API keys require their actual cause to be fixed.
The container memory policy is unchanged.

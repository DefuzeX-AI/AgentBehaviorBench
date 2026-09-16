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
| Docker unavailable / permission denied | Run `docker info` as the same user. Start Desktop/Engine and inspect Docker context/permissions. Do not run ABB as root to hide ownership problems. |
| Missing/invalid KUMA key | Nonempty `KUMA_API_KEY` takes precedence over `DEFUZEX_API_KEY`. Check exported variables overriding `.env` and service account access without displaying keys. |
| Missing model / quota / provider error | `OPENROUTER_MODEL` has no runtime default. Check the slug, account access, funds/limits and tool/protocol support. A key is not a model name. |
| `agent add -b` rejects model response | Requires strict structured outputs. Inspect `cache/onboarding/…` to distinguish schema incompatibility, output exhaustion and timeout. |
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

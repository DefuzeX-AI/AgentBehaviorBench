# Troubleshooting and results

Start with `python -m examples.offline_demo`. It needs no credentials or Docker.
If it passes, check `docker info`, the enabled registration and local `.env` before
attempting a paid Run. `agentbench sdk list` should show `kuma`.

| Symptom | Check and next action |
| --- | --- |
| No ready Agents | `run` selects enabled ready entries only. Evaluate the adapting Agent, then run real certification. Do not edit status to bypass it. |
| Cannot import `kuma.repository.case_artifacts` | Use the project interpreter; run `python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt`. The pinned PyPI 0.2.4 includes this module. Installing on the host does not rebuild a Docker image. |
| Missing model or credential | Set the required values locally. The template model is an example. `KUMA_API_KEY` takes precedence over `DEFUZEX_API_KEY`; exported environment takes precedence over dotenv. |
| Command waits on stdin | Use `--yes --no-view`. `--no-view` alone only disables the viewer. |
| Invalid/retired strategy group | Compare the profile with the current official Kuma strategy group catalog for your account. Do not guess another identifier. |
| Timeout or connection failure | Inspect the SDK code/request ID and per-Case `network.jsonl`. SDK and related network errors are distinct observations. Preserve the original request record before retrying; an unknown response may already have incurred a charge. |
| Judge received, host rejected | The failed Case's `artifacts.received_report` locates the report and marks `host_accepted=false`. Diagnose the trace/identity failure; a received report alone does not establish successful execution. |
| Judge reports `issue` | Read its reason and evidence. This is a behavioral result; `evaluate` exits 1. It does not imply the adapter failed. |
| Tool content absent | Inspect per-Input `capture-status.json`. A root span alone is not tool evidence. Values may be omitted for sensitivity, size or schema reasons; do not invent missing fields. |
| One Case fails | Other finished Cases remain in the result snapshot. Inspect each Case status and error. Cancellation explicitly records unfinished work. |

The ABB JSON file is an event list, ending with `suite_completed` when finalized.
It contains per-Case results and report/artifact references. Reopen the exact printed
path with `agentbench view PATH`. The SDK output directory retains original Case,
Run manifest, Agent outputs, report, capture status and request records. Keep these
for diagnosis, but do not publish raw logs or credentials.

An illustrative outcome (not a service-generated report):

```text
Case A: execution completed; Judge pass
Case B: execution completed; Judge issue (behavioral finding)
Case C: execution failed; Judge received; host_accepted=false
```

Check the [official Kuma diagnostics](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/public-error-diagnostics.md)
and [trace contract](https://github.com/DefuzeX-AI/KUMA-DefuzeX/blob/main/docs/runtime-trace.md)
before changing SDK behavior. ABB fixes orchestration and adapter faults; service
authorization, balance and server failures require the service/account owner.

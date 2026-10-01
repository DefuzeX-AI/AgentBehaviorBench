# ABB Viewer — Vite + React + Redux

A local multi-Case Suite overview and per-run evaluation, OTel and interaction details.

## Install and view results

The host needs npm and Node.js 20.19+ on 20.x, or 22.12+, as required by the locked
Vite dependency. Python installation does not install web dependencies or build dist/.

```sh
cd web
npm ci
npm run build
cd ..
# Use the actual result path printed by an evaluation or offline demo.
agentbench view results/suites/<suite-id>/events.json
```

Normal view serves web/dist and result APIs through Python; no npm development
server is needed. Build after cloning or frontend changes. Headless evaluation
uses --no-view and can skip Node and the build. Keep the viewer command running
and open its exact printed URL. dist/index.html is not a standalone report: opening
or sending that file alone cannot provide the full evaluation page.

## Frontend development

After npm ci:

```sh
cd web
npm run dev
```

Open the printed local address. The sidebar lists runs under results/observe/ and
selects the newest entry by default. Select a run to combine its framework and
network traces; refresh to update the list and contents. Entries identify individual
runs by artifact directory ID, not by Agent name. The list uses generic metadata
(agent_id, run ID, status and modification time), not business-specific input fields.

Missing traces, malformed files and read failures show diagnostics. You can also
import multiple trace files manually:

- `results/observe/<run-id>/network.jsonl`
- `results/observe/<run-id>/invocation-*/output/framework.jsonl`

Events appear in time order, with search, source filtering and expandable JSON.
A new file selection replaces the current list. JSON event arrays are supported;
each record needs event, so run.json is not a trace input file. Malformed lines are
reported and skipped. Each import is limited to 20 MB, with 100 entries per batch.

server/runs.js provides the run API in Vite dev and preview modes without a separate
Python server. It permits local same-origin GET requests and confined artifact
reads, rejects path traversal and limits reads to 20 MB. Manual imports stay in the
browser. Local artifacts refresh every second. OTel supports graph and tree views
with payloads loaded on demand.

Python view serves the built UI and bound run events. If assets are missing or
incomplete, CLI preflight exits with build instructions. A bound Suite displays
all Agents and Cases and supports expanding several Cases simultaneously.

## Execution replay

The Replay tab is available in a Case attempt and the standalone run viewer.
Play, pause, step in either direction, seek, adjust speed, and skip long waits.
Conversation, tool/MCP and network calls share the recorded timeline; overlapping
calls remain concurrent. Responses appear only after their recorded end. Select
an event for its request/result, or a workspace path for its captured content and
previous version. Refresh records explicitly when inspecting a running attempt.

New execution runs store local workspace history in `replay/` beside
`evaluation/` in the run directory. A separate `/run/abb-replay` host mount keeps
it outside the observed workspace and KUMA repository. Replay files are not added
to SDK submissions, Judge context, or trace evidence. Existing evaluation
evidence and its configured upload policy are unchanged.

The recorder observes the declared evaluation workspace, otherwise the ACP
working directory or the worker's current directory. It saves a baseline, watches
Linux file notifications with periodic reconciliation, and captures each Input
boundary and final Agent cleanup. Other hosts use sampling. Times describe when
versions were observed, not exact write times or inferred tool causation. Rapid
writes can merge; files created and removed between captures may not appear.

`.git` and `.kuma` directories are excluded. Links and special files are not
followed; sensitive paths, binary files and files over 2 MiB retain metadata only.
Known environment credentials are redacted in text. Content is deduplicated by
hash, with 256 MiB of content, 10,000 paths, 100,000 events and 32 MiB of event
metadata per run. Limits and capture failures are shown as partial coverage;
recording failures do not change the Agent's execution or Judge verdict.
Old runs retain conversation/call replay and explicitly show that historical
file versions are unavailable. Replay is read-only and never re-executes tools.

## Suites and recovery

The Suite page reads a unified Python snapshot. Redux manages snapshot revision,
filters, expanded rows, selected historical attempts and recovery commands.
Execution state and Judge verdict are displayed separately. Details use the
attempt's artifact_run_id, without guessing from Agent names. A disconnect preserves
the current content until reconnection; historical selections do not jump to a new attempt.

Controlled sessions offer continuation and per-Case recovery. Read-only history
hides recovery actions. Commands include the server's control token and an idempotent
command ID; uncertain responses are retried with that same ID. Export current report
downloads a JSON snapshot with Cases and attempt history, excluding control credentials.
It does not bundle every trace or generate standalone HTML; see
[sharing results](../docs/Troubleshooting.md#share-a-report).

To develop against a running Python viewer:

```sh
ABB_VIEWER_BACKEND=http://127.0.0.1:<viewer-port> ABB_SUITE_ID=<suite-id> npm run dev
```

Set both values together. Vite proxies /api to that local viewer and injects the
exact Suite API path; recovery rules remain in Python. Without these values, the
read-only standalone run directory API remains in use. Do not set these development
variables when building distributable assets: Python binds production pages to a Suite.

```sh
npm test
npm run build
npm run preview
```

See [README](../README.md), [the operation guide](../docs/Guide.md), or
[中文操作指南](../docs/otherLanguages/Guide.zh-CN.md) for setup.

# Suite recovery and multi-Case viewer

Implemented against the PyPI KUMA 0.2.4 adapter. This extends the existing shared
Case worker pool; it does not replace the SDK's Case, Run, request, or Judge APIs.
Memory and multi-turn conversation design changes are deferred at the user's
request on 2026-09-14. Subsequent campaign acceptance uses single-turn Cases.

## Running and continuing

Normal directory-SDK runs now print a durable path:

```text
results/suites/<suite-id>/
  plan.json
  events.json
  cases/<agent>/<slot>/case.json
```

A custom output base places `suites/` beside that base. `events.json` remains a
JSON event array accepted by the existing result viewer. Arbitrary injected
Python runners still support the legacy exporter; their configuration is not
invented to make them appear recoverable after a process restart.

```bash
# Continue the same evaluation without rerunning completed Cases.
agentbench resume results/suites/<suite-id>/events.json

# Explicitly recover one unfinished slot; Case numbers start at 1.
agentbench retry results/suites/<suite-id>/events.json --agent react-agent --case 3

# Open all Cases and attempt histories, with eligible recovery controls.
agentbench view results/suites/<suite-id>/events.json

# Disable automatic Case retries for a new run.
agentbench run --case-retries 0 --yes --no-view
```

CLI recovery and the viewer call the same coordinator. After code/model changes,
`resume` refuses to merge evaluations with different provenance. Use
[`agentbench reuse`](Case-Reuse-Commands.md) to create a linked new Suite from the
same immutable Cases. It records fresh provenance and copies no old output,
Attempt, SDK Run, or Judge result.

## What is retained

The Suite plan fixes selected Agents, Case positions, non-secret options,
source/dependency fingerprints and SDK distribution versions. A platform file
lock permits one writer per Suite. Readers consume atomically published files.
Ordered events provide the single source for the current snapshot and report.

Each generated Case is validated and retained before it becomes executable.
Partial generation keeps successful slots and records separate failures without
renumbering. Resume generates only eligible missing slots. A lost or modified
file from an already saved slot requires restoration of the original bytes;
other slots remain usable. An ambiguous CaseGen request is never treated as
permission to submit a replacement request.

Every dispatched Attempt has a durable identity before worker submission. A new
Case execution gets a new Attempt/Run. Recovery of an already accepted Judge
request stays within its original Attempt. Retry history and its remaining
budget/backoff survive restart. Cancelling during backoff retains the original
failure and request artifacts while marking the pending retry cancelled.

The default retry policy permits two extra attempts with bounded exponential
backoff and jitter. The adapter must provide an explicit recovery action and
automatic permission. Waiting retries release their worker slot. Shared SDK
generation failures pause queued preparation; accepted Cases can still finish.

## Execution, verdict, and evidence are separate

| Situation | Result and recovery behavior |
| --- | --- |
| Judge reports `pass` or `issue` with accepted evidence | Completed Case. Preserve verdict; do not automatically rerun it. |
| Safe transient execution failure | Save failure, schedule bounded retry using the same Case. |
| Agent completed; original Judge request is pending | Verify original artifacts and cleanup, then resume that public SDK request. |
| Report already saved but Suite summary missing | Validate and accept the saved original report; do not rerun Agent or Judge. |
| Judge terminal `model_invalid_result` | Needs attention; do not reopen a terminal request or loop automatically. |
| Report received but host rejects evidence/trace | Retain received report and rejection separately; do not count as host accepted. |
| Original request acceptance or resource cleanup uncertain | Keep the Case blocked until its original operation can be reconciled. |

The report counts planned Cases, execution completions, received Judge reports,
host acceptances, pending/blocked slots and verdict distribution independently.
Shell exit policy is preserved: a Judge finding can return nonzero even though
the evaluation pipeline completed correctly.

## Viewer behavior

Redux Toolkit stores the authoritative Suite snapshot, revision, filters,
expanded Cases, selected historical Attempts and command acknowledgments. All
planned slots are visible before their Run artifacts exist. Several Cases can
be expanded at once. An opened historical Attempt remains selected while new
attempts arrive; exact artifact identity prevents showing a different Run.

Polling updates execution stages, temporary failure, retry countdown, recovery
and final results. Disconnection keeps the last snapshot visible. The partial
JSON export includes current results and all attempt history, excluding the
viewer control token.

The loopback Python API validates origin, Suite binding, command shape, token,
revision and idempotent command ID. HTTP threads enqueue work; a dedicated
coordinator performs it under the Suite lock. Vite proxies this same API. Old
standalone reports remain viewable without recovery controls or valid execution
credentials. Closing a browser tab does not cancel work; closing the owning CLI
viewer stops its queued/active recovery controller.

## Module boundaries

| Directory/module | Responsibility |
| --- | --- |
| `harness/scheduling/` | Seeds, per-Agent state, partial preparation and retry policy. |
| `harness/scheduler.py` | Bounded worker admission, delayed retries and cancellation. |
| `harness/session/` | Plan, locks, immutable Cases, codecs, event projection and artifact references. |
| `cli/sessions/` | Fresh publication, saved runner reconstruction, resume/reuse, viewer command lifecycle. |
| `sdk/contracts.py` | SDK-neutral prepared Case batch and per-slot failure contracts. |
| `sdk/plugin/kuma/` | Public KUMA save/reuse/request recovery and KUMA error classification. |
| `observe/suite_reader.py`, `cli/viewer_control.py` | Canonical snapshot/artifact reading and HTTP commands. |
| `web/src/suite/` | Redux state, multi-Case components, attempt selection and commands. |

Retry timing, worker limits, model settings and SDK package names come from
configuration/contracts instead of Agent-specific branches in the scheduler.
`[evaluation] replay_safe` remains an explicit per-Agent declaration; the three
configured research bindings were separately audited before enabling it.

`clean` protects persisted Suite directories and every referenced Attempt,
including historical results and custom-output Suites registered in the local
reference index. A malformed reference blocks archival rather than guessing.
Legacy unreferenced history can still move into the recoverable archive.

## Verification and remaining limits

Regressions cover 30 planned Cases with 20 completed followed by resume of only
the remaining 10; partial generation; immutable file corruption/restoration;
original-request recovery; retry exhaustion; cancellation; concurrent writers;
duplicate commands; failed publication; changed provenance; and linked reuse.
These are deterministic fault-injection fixtures, not paid service claims.

See [SDK container verification](Kuma-Case-Recovery-Verification-2026-09-14.md),
[browser acceptance](Suite-Viewer-Browser-Acceptance-2026-09-14.json), and
[live smoke evidence](Live-Recovery-Smoke-2026-09-14.json). Paid calls are recorded
in the [existing campaign ledger](Benchmark-Campaign-Ledger.json).

Recovery requires provable original artifacts. Abrupt process death with an
unconfirmed live container or incomplete host trace can remain blocked; this
implementation does not reconstruct arbitrary Agent memory or pretend cleanup
occurred. The public SDK cannot turn every terminal Judge failure into a new
Judge-only evaluation, nor does a successful CaseGen request status necessarily
provide an exportable Case file. Those cases retain evidence and a clear reason.

Provenance covers source files, declared requirements, public settings and host
SDK distribution versions. It does not yet pin the resolved Docker image ID,
base image digest or every container dependency version. Rebuilding a mutable
base image or dependency range can therefore change runtime bytes without a
source change; this is not a guarantee of bit-identical execution environments.

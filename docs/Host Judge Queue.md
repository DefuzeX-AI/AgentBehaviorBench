# Host Judge queue

Official KUMA benchmark execution separates Agent containers from Judge waiting.
The container runs the saved Case with `judge=False`, commits SDK evidence, and
exports the public Case and History. ABB validates the original Case identity,
input/output/submission correlation, trace acceptance and Docker cleanup before
persisting `judge-task.json`. The host calls KUMA's
`OfficialJudgeProvider.judge(JudgeContext)`; KUMA owns upload serialization,
dynamic limits, privacy checks, request identity, polling and report normalization.
ABB does not recreate a Run or execute the Agent to submit Judge evidence.

## Scheduling

- `ABB_MAX_PARALLEL_CASES` bounds preparation and Agent execution (default `1`).
- `ABB_MAX_PARALLEL_JUDGES` bounds independent host Judge workers (default `2`).
- `ABB_JUDGE_QUEUE_CAPACITY` bounds waiting tickets plus reserved execution slots
  (default `8`). Active Judge workers have their own bound. When capacity is full,
  new execution admissions pause until the queue drains. Lower capacity can reduce
  effective execution concurrency.

Judge admission uses FIFO order within a running coordinator. After restart,
pending work is reconstructed from the saved Suite's Case slots; an interrupted
task keeps its identity, but its original global queue position is not guaranteed.
Containers, their runtime services and execution
slots are released before tickets enter the queue. The coordinator waits for both
pools before producing the final Suite result. The local SDK plugin retains its
existing local Judge flow.

Install the host KUMA dependency as well as the container dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "kuma-defuzex[otel]>=0.3.3"
python -m agentbench run
```

These settings are frozen in a saved Suite's configuration and reused on recovery.

## Persistence and recovery

Each Attempt retains `evaluation/judge/context.json`, original per-input artifacts,
their SHA-256 digests in `judge-task.json`, and a host-owned `judge-state/.kuma`
request ledger. Credentials are obtained at runtime; only their SHA-256 identity
is sealed in the task. Switching credentials cannot create a replacement Judge.
An OS writer lock prevents concurrent hosts from processing one ticket. Changed
evidence, incomplete cleanup, mismatched IDs and invalid SDK contracts block upload.

Task states are `queued`, `submitting`, `judging`, `completed`, `interrupted` and
`failed`. Successful reports remain in `evaluation/judge/report.json`. Recovery
retains the original Attempt and SDK Run. An accepted operation is polled through
its existing identity; an uncertain POST is reconciled by KUMA. A confirmed
terminally failed operation is not automatically replaced with another paid task.
Automatic recoveries use the existing bounded Suite retry budget and backoff.

Judge delivery, Agent execution, and host evidence acceptance are independent.
A committed native Agent failure can still have accepted evidence and a completed
Judge task. Its original per-input errors are retained in the benchmark's
`failures`, and its execution status and quality gate remain failed, even if the
Judge returns `pass`. A received report never triggers another Judge submission.
The host revalidates saved reports locally before returning them, including reports
whose older task record incorrectly marked native execution failure as Judge failure.
Submission failures retain both the SDK error and any preceding native Agent error;
they do not enter the Judge queue. Cleanup, trace and identity gates remain required.
The viewer revalidates older retained reports through the SDK's offline result
reader. It corrects the displayed acceptance and native error only after the
original sealed evidence, Case and Attempt identities pass validation. Raw events,
reports and task files remain unchanged; this projection performs no network calls.

Closing or reopening the webpage does not affect either pool. Stopping the CLI
stops processing; it does not install a background service. Continue saved tasks
with the normal `agentbench resume SUITE` command. A crash after evidence export
but before enqueue is reconciled from the saved execution only after cleanup and
trace acceptance have been confirmed.

Cancellation is checked between SDK HTTP calls. An in-flight call can take up to
its configured transport timeout before the worker returns.

## Viewer and timings

Persisted events distinguish Judge queued, submitting evidence and waiting for an
accepted request. The Overview and Judge tabs show these states independently of
the final verdict. Host queue waiting and Judge request intervals appear alongside
container timings; they survive viewer restarts. SDK request duration includes
upload, network, server waiting and polling; it is not server model compute time.

## Offline acceptance

`tests/sdk_fixtures/deferred_judge.py` runs the native SQLite Agent and real KUMA
worker in an existing container with networking disabled. It exports committed
evidence and exits without calling Judge. Host tests use the real
`OfficialJudgeProvider` with controlled Backend responses to verify one submission,
GET-only recovery after an accepted POST, complete contract round trips and report
publication. This verifies the handoff, not a production LLM's behavioral verdict.

The final local acceptance retains Case, Agent output and a controlled Judge report
under `results/verification/deferred-judge-final/`. The acceptance records explicitly
identify controlled Backend responses and no production service calls. The SDK
warns `file_observation_summary_unavailable` for these isolated fixtures; they do
not demonstrate complete production filesystem observation. The opt-in fresh PyPI
image build and older SDK container test were skipped in the regression batch;
the new handoff was separately verified in a cached Docker image with KUMA 0.3.3.
The raw Windows SIGINT integration test was excluded; cooperative cancellation,
pending-ticket retention and accepted-request recovery were verified separately.

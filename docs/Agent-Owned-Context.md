# Agent-owned context

Decision approved on 2026-09-14: BBA delivers each current Case Input and keeps
the Agent execution session alive. The Agent owns conversation context, memory,
compression and its own files or SQLite database. BBA does not implement a
memory backend or generate an Agent-specific multi-turn prompt.

## Execution contract

1. Start an isolated execution environment for one Case attempt.
2. Load the Agent once and use one stable session identity for its Inputs.
3. Deliver the current Input, wait for the answer and submit it to KUMA.
4. Continue sequentially until the Case ends, then collect the Judge report.
5. Close the Agent session and remove the execution environment on all exits.

Different Cases can run concurrently. A replay starts a new Run/session and must
not inherit the preceding attempt's mutable memory. KUMA's immutable history and
BBA's artifacts remain evaluation records; they are never injected back into an
Agent automatically. An Agent can still receive structured history when that is
literally the SDK-provided Input, without BBA modifying it.

`evaluation/input-contract.json` now contains only `{"encoding": "identity"}`.
The old `conversation` modes fail preflight with a migration error. Native field
mapping and output extraction remain supported by the existing framework adapter.

## Runtime and storage

The KUMA worker executes all Inputs in one container process, sharing a single
`AgentSession`. It closes that session after the Run. The generic worker supplies
the stable session identity as LangGraph's `configurable.thread_id`.

The existing Docker policy provides a private writable `/tmp` for the lifetime
of the container (64 MiB by default). Agents can put their own SQLite database or
files there using their normal configuration. No database API, schema, read/write
algorithm or conversation summarizer is implemented in BBA. Image source paths
remain read-only; applications that write relative to their source directory
must configure a writable location. Container removal discards temporary state.
Larger storage, external databases and deliberate cross-session memory tests are
future explicit requirements, not implicit shared storage between Cases.

Keeping a process alive does not give a stateless Agent memory. Document the
capabilities of the exposed entrypoint and any native framework options enabled
for deployment. Do not interpret successful multi-turn delivery as proof of
correct recall. Do not change a research endpoint into a report-chat endpoint
without explicitly changing the evaluated application.

The separate generic Docker `oneshot` invocation starts a fresh process for each
call. It remains suitable for standalone `observe`; it does not promise in-memory
conversation continuity in custom SDK loops. KUMA's whole-Case worker is the
supported persistent evaluation path in this deployment. A native service caller
can also preserve state through its own existing runtime protocol.

## Validation stages

- Stage 1: remove BBA history augmentation; validate current-only payloads and
  preserve SDK evidence, submission and recovery behavior.
- Stage 2: migrate bundled Agent bindings and capability documentation without
  introducing per-Agent conversation policies.
- Stage 3: exercise actual Agent-owned storage in a real container with multiple
  Inputs, fresh-Case isolation, lifecycle cleanup, Case/output/Judge artifacts,
  then run the relevant regression suite.

Each stage is tested and committed separately to the fork's `main` branch.

### Input migration validation

The core input migration and bundled binding changes are committed together so
the fork never contains a driver that is incompatible with its bundled Agents.
Validation: 154 passed / 2 opt-in tests skipped across SDK directory/PyPI,
input-contract, evidence, preparation, request recovery, retry and Suite resume
tests; 32 passed / 2 opt-in tests skipped in `tests/test_issue39.py`.
The latter runs the original ReAct builder with its native InMemorySaver and
offline model/tool transports to check retained history without duplication.

All three changed deployments are returned to `adapting` until real certification
of the new input behavior succeeds. Historical campaign records are retained;
history-replay runs do not certify the new Agent-owned context configuration.

### Session and SQLite validation

The production KUMA worker, PyPI SDK 0.2.4, generic AgentSession, framework
adapter and LangGraph execute normally in the acceptance tests. Only the remote
Case/Judge providers are replaced with explicit deterministic local providers.
The fixture Agent creates and queries SQLite itself; BBA does not access its
database during execution. A shared Case rejects conflicting `thread_id` values.

Validation: full Python suite **430 passed, 9 opt-in tests skipped**. The socket
tests require local loopback permission; the sandbox-only attempt could not bind
their HTTP server, and the complete suite passed with that permission. Explicit
session acceptance **7 passed**, including three overlapping containers under
the production Docker policy, non-root and with network disabled. Each container
used `/tmp/session-work/case/agent-memory.sqlite3`; no state crossed containers.

The five-turn Case recalled a value, updated it and recalled the correction.
A fresh Case returned `unset` before learning its own value. Failure/cancellation
tests preserved previous submissions and closed the Agent database once. All
actual input artifacts contain only the corresponding SDK Input.

See [the acceptance record](Agent-Owned-Context-Acceptance-2026-09-14.json) for
retained Case, Agent output, evidence, Judge and session artifact paths. These
are real container runs with local Judges, not paid model or official Judge
acceptance. Real deployment certification is recorded separately.

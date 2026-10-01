# Runtime timings

Open a Case and select **Timing**. The default flow shows saved shared Case
preparation before the selected execution attempt. Generation operations are
visible immediately; expand preparation to see its Docker setup and all other
operations. Shared preparation has its own measured total and is not charged to
each attempt. Individual preparation runs remain selectable through Timing scope.

Sequence uses one continuous canvas. Each participating lane keeps the same
position throughout the Case, including SDK submissions and later Inputs. The
initial non-call steps are folded into **Before first action**; trailing steps
are folded into **Finishing steps**. Open either block for its original operation
tree, including Docker setup, image resolution and service startup. Small
bookkeeping steps between calls remain compact rows at their recorded start
positions. Unknown operations remain inspectable with their recorded names.

Agent calls and SDK submissions share an Input heading only when an explicit
Input ID identifies a unique Agent operation in the same execution phase.
Missing or ambiguous IDs keep operations separate. These are presentation groups,
not new parent-child relationships. Total/container/Case envelopes provide
context without duplicating every nested operation in the main view.

Click a stage or Input heading to open its complete step tree in the right drawer.
Selecting a step shows elapsed time, time outside measured children, status and
its complete saved timing record. OTel steps also expose input, output and other
trace payloads on demand. The drawer preserves parent-child nesting, rather than
presenting overlapping parent and child durations as an additive breakdown.

Only lanes participating anywhere in the flow are displayed. A single header and
continuous lifelines connect all Inputs; filtering keeps these positions fixed.
Rows remain continuous without sequence pagination. The optional filter shows
the three longest groups. Overlapping Input groups also label their individual
call cards with the Input ID. Bars compare calls within each Input rather than using
the full run's time range. File snapshots appear after the Input's last recorded
call, including its SDK submission. Vertical spacing is not proportional to
elapsed time. Nested and parallel calls overlap.

Group totals use the union of measured root intervals, excluding gaps and counting
nested children once. Individual calls and intervening bookkeeping remain in
recorded start order even when different Inputs overlap. Visual order does not
infer data dependencies; use Waterfall for a proportional time axis. Shared
preparation is a linked prerequisite displayed separately, not an invented parent
call from the execution attempt.

Solid arrows require recorded parent-call or
framework-span links. Dashed return arrows require a confirmed end. Cross-process
placement and nearby timestamps alone do not imply a call relationship.

The auxiliary **Waterfall** view supports expanding groups, panning, Ctrl + wheel
zoom and **Fit all stages**. The table below supports duration sorting and
keyboard selection. The selected Sequence/Waterfall view is retained in the URL.

**Timing scope** also exposes saved shared Case preparation runs when available.
Batch preparation is recorded once, rather than charged to every Case.

## Persistence and interpretation

Timing collection runs in the execution processes, independently of the viewer.
Reopen the saved Suite with `agentbench view` and select the same Case, or reopen
its URL. Case, Timing tab and historical attempt selections are in the URL.
Closing the browser does not stop timing collection or the evaluation. The local
viewer server must be running to serve the page.

- `timing.jsonl` stores host operation snapshots in each evaluation artifact.
- `evaluation/timing.jsonl` stores worker operation snapshots.
- `timing-recovery-<id>.jsonl` stores each Judge recovery attempt separately.
- Existing per-input OTel files supply framework/model/tool calls. Their original
  evidence is not modified by the timing view.
- Start and end snapshots are written immediately. Active operations checkpoint
  every two seconds. Lifecycle durations use the process's monotonic clock;
  UTC anchors arrange processes on one timeline. Cross-host clock skew can
  affect visual alignment; cross-process offsets are not precision measurements.
- The completed attempt total includes dispatch and final validation. The
  recorded evaluation time covers host staging through cleanup. Judge recovery
  stages stay on their original Attempt, and their recorded time is included.
  A completed Attempt's elapsed time also includes gaps before recovery; the
  recorded evaluation total includes only measured host execution intervals.
  Queue and retry-backoff records remain separately inspectable and are not included in that attempt total.
- Nested calls and parallel operations overlap. Do not add all row durations.
  “Outside measured children” is uncovered elapsed time, not CPU time. Its value
  is omitted when child intervals come from incomparable process clocks.
- KUMA's `submit()` may include evidence processing and remote judgment. Until
  those boundaries are exposed, this is labeled **Submit output / wait for SDK**.
  This is client-observed latency, not a measurement of server compute time.
- If a process stops reporting, its unfinished operations become **unconfirmed**
  after 15 seconds. The viewer retains the last measurement and does not keep
  counting. A missing end is never relabeled as successful.
- Older runs show the traces they actually contain. Missing lifecycle durations
  are marked **Not recorded**; file modification times are not used as substitutes.

## Implementation

### Submission errors and local diagnostics

ABB submits successful native output and failed/timeout/aborted native error text
to KUMA after credential redaction. Failure text is not replaced with a generic
diagnosis; line breaks and empty or missing errors retain their original values.
This does not upload all local diagnostics: KUMA still applies its own Trace
allowlist and capture limits. An underlying tool error swallowed by the Agent
and retained only in local stderr is not automatically part of its final error.
Inspect the saved `inputs/*/submission.json` for the SDK's committed evidence.
Historical submissions and Judge reports are unchanged; new execution attempts
use the corrected error forwarding.

### File changes in the sequence

Each Input can show file and directory cards from its saved `file_evidence`.
Green means created, red deleted, blue modified, and purple a recorded move or
rename. Labels and symbols accompany colors; deletion does not mean failure.
Hover or focus shows the full path and evidence basis. Clicking opens the same
details drawer with the captured diff and original record.

The file viewer uses lazy-loaded `@pierre/diffs` components for line numbers,
colored additions/deletions, and word-level changes. The drawer uses a unified
diff; Expand offers a side-by-side view. Raw patch and copy remain available.
New Markdown files open as rendered text when the evidence contains the complete
file; other complete files receive syntax highlighting. Deleted files can show
their previous content. Full previews require complete evidence, contiguous
hunks from line one, a matching `/dev/null` header, and a matching captured byte
size. Partial or modified-file patches remain diffs; malformed and oversized
patches fall back to the original text without truncation.

These are before/after snapshot differences, not filesystem events. They appear
after the matching Input, never at an invented timestamp or on an inferred tool
call. Ambiguous or missing Input associations remain in a separate summary.
Files created and deleted within one Input may be absent from the net diff.
Partial evidence and missing evidence remain distinct from a complete empty diff.
Initial historical records are static; newly received changes briefly highlight,
respecting reduced-motion preferences. No benchmark rerun is needed for saved
file evidence. File UI components and normalization live in `web/src/files/`.

`agentbench.observe.timing` supplies context-local instrumentation shared by the
host and worker. `agentbench.observe.timeline` reads the journals for the Python
viewer and Vite's local bridge. `/api/observe/runs/<run>/timeline` is read-only and
uses the existing Suite artifact access checks.

The React `CaseTimeline` component defaults to the shared `SequenceDiagram`, also
used by Execution flow's Sequence lanes. Its auxiliary waterfall uses
[vis-timeline](https://visjs.github.io/vis-timeline/docs/timeline/), loaded only
when selected. Its range items, nested groups and millisecond scale fit execution
waterfalls. Labels use text nodes, and editing timeline records is disabled.

Timing also offers **Topology**, an aggregated participant graph built from the
saved attempt. Repeated Agent, model, tool, HTTP and SDK calls are grouped by
kind and recorded name (and model ID when available). A Case runner node keeps
the actual caller of Agent turns and SDK submissions visible. Intermediate
framework spans are traversed only along recorded parent links. Cross-process
links require a matching invocation ID; disconnected records stay disconnected.
Docker preparation remains in Sequence and Waterfall.

Nodes and connections show counts and summed recorded span durations. These are
not wall-clock totals: nested and concurrent calls can overlap. Missing timings,
unfinished calls and failures remain explicit. Select either a node or a
connection to inspect its saved calls and descendants in the existing details
drawer. The graph supports pan, zoom and fit-to-view using the existing React
Flow dependency. `timingView=topology` in the URL restores the view on reopening;
no new benchmark execution is needed when the saved calls are available.

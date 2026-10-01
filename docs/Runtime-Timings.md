# Runtime timings

Open a Case and select **Timing**. The default **Sequence** view groups environment
and Docker preparation into one stage, with separate SDK bookkeeping and final
validation/cleanup stages. Agent execution is grouped by recorded Input identity
and parent-child relationships. Framework wrappers stay in the detail tree;
Agent turns, typed model/tool calls and SDK waits remain visible in the main view.

Click a stage or Input heading to open its complete step tree in the right drawer.
Selecting a step shows elapsed time, time outside measured children, status and
its complete saved timing record. OTel steps also expose input, output and other
trace payloads on demand. The drawer preserves parent-child nesting, rather than
presenting overlapping parent and child durations as an additive breakdown.

Only participating lanes are displayed in each Input. Rows are compact and
continuous, without sequence pagination. The optional filter shows the three
longest groups. Bars compare group summaries at the top level and calls within
each Input; they do not all use the full run's time range. Vertical spacing is not
proportional to elapsed time. Nested and parallel calls overlap.

Group totals use the union of measured root intervals, excluding gaps and counting
nested children once. The environment group also includes recorded queue/dispatch
time, so it can differ from the Preparation summary. SDK bookkeeping may span
several parts of the run; its group is explicitly labeled **Across this execution**.
Unknown or ambiguous Input identities remain in separate groups.

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
  Queue and retry-backoff records remain inspectable in the environment group's
  drawer and are not included in that attempt total.
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

### File changes in the sequence

Each Input can show file and directory cards from its saved `file_evidence`.
Green means created, red deleted, blue modified, and purple a recorded move or
rename. Labels and symbols accompany colors; deletion does not mean failure.
Hover or focus shows the full path and evidence basis. Clicking opens the same
details drawer with the captured diff and original record.

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

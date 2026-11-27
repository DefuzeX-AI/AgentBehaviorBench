# ABB ATIF and subagent association experiment

## Scope and implementation

This started as an explicit host-side experiment. It leaves `trajectory/builder.py`,
`trajectory/schema.py`, Judge/GT contracts, collectors and the desktop application
unchanged. The run flow now also derives the document for every attempt; see
[Automatic derivation](#automatic-derivation). Harbor is never installed into an
Agent image.

## Automatic derivation

After the container stops, `run_evaluation` and `observe` call
`agentbench.trajectory.atif.attempt.write`. It saves `trajectory.atif.json` in the
attempt directory and returns the `atif` entry of `run.json`:

| `status` | Meaning | File written |
| --- | --- | --- |
| `complete` | Converted without evidence issues. | yes |
| `partial` | Converted; `issues` counts the gaps listed inside the document. | yes |
| `failed` | Conversion raised; `error_type` and `error` say why. | no |
| `unavailable` | Harbor is not installed. | no |

None of these changes the execution outcome.

Only `harbor.models.trajectories` is imported, and it needs pydantic alone.
Install Harbor without its own dependency tree (Python 3.12 or newer):

```bash
python -m pip install --no-deps -r agentbench/trajectory/atif/requirements.txt
```

A full Harbor install adds about ninety packages and can downgrade ones ABB
already uses. The pinned commit must equal `HARBOR_COMMIT` in
`agentbench/trajectory/atif/__init__.py`; `provenance.py` rejects any other.

Delegation adapters remain an explicit choice. An Agent unit selects them in
`agent.toml`, and the choice is frozen into `request/target.json`:

```toml
[atif]
adapters = ["openclaw"]
```

A unit that declares nothing gets a root trajectory without embedded subagents.

### Step sources

Which recorded evidence becomes the model and tool steps is decided by one step
source per attempt (`agentbench/trajectory/atif/sources/`). The source is chosen
from the unit frozen in `request/target.json`, never from an Agent's name:

| `[adapter] type` | Source | Model steps | Tool results | Reply |
| --- | --- | --- | --- | --- |
| `langgraph` with `langfuse-auto` | `langfuse` | Langfuse generation spans in `otel/spans.jsonl` | Langfuse tool spans | The delivered result follows the LangGraph reply rule below. |
| `langgraph` with legacy callback evidence | `langgraph` | LangChain callbacks in `framework.jsonl` | LangChain callbacks | When the final root model step of the same turn has no tool calls and its message exactly equals the delivered text, its `extra.abb.result_source` points to the result file. Other delivered text gets its own `invocation_result` step. |
| `acp` | `acp_otel` | Inference spans the Agent exported to `otel/spans.jsonl`, merged with the interceptor's model calls | Tool spans the Agent exported, merged with the tool calls reported over ACP | The last model step of the turn; the delivered result is not repeated. |

A unit overrides the default with `[atif] source = "<name>"`. An adapter type
without a source, or an unknown source name, fails the derivation with that
reason. Without a frozen adapter type (a standalone observe run) the
`framework` recorded in the invocation requests decides; an attempt that
recorded neither is read with `langgraph`. A format that needs its own reading adds a module to `sources/`
and registers it in `sources/__init__.py`; the shared reader, ownership,
assembly, validation and stored form do not change. Only `acp_otel` converts
the interceptor records in `logs/network.jsonl`.

`acp_otel` reads nothing ABB wrote while relaying ACP: the tool spans and ACP
message copies in `framework.jsonl` are not a step source.

#### Three records, one timeline

An ACP Agent's run is recorded three times, each on its own clock:

| Record | File | Holds |
| --- | --- | --- |
| `trace` | `otel/spans.jsonl` | Model calls and tool executions the Agent exported |
| `network` | `logs/network.jsonl` | Every model call, as the interceptor saw it on the wire |
| `acp` | `steps/NNNN/acp-events.jsonl` | Each prompt's start, tool call reports, reply text |

`sources/merge.py` folds them into one set of records. An operation several
records hold becomes one step that names them in `extra.abb.sources`; an
operation only one of them holds is kept and names that one.

| Operation | Same operation when | Compared records |
| --- | --- | --- |
| Model call | The emitted tool call ids are equal, or the text when no tool call was emitted. Equal outputs pair in recorded order. | `network`, `trace` |
| Tool execution | The tool call id is equal and one ACP session reported it. | `trace`, `acp` |
| Reply text | The text a session sent, cut at tool calls and prompt boundaries, equals a model call's text. | `acp`, model call |
| User message | Only ACP records when a prompt was sent. | `acp` |

Time never pairs two records. It only orders the merged ones:

- a step is dated by its span start; without a span by its ACP report; with
  only a wire record by the request time minus 140 ms, the median lead of a
  span over its wire request in the recorded runs (`NETWORK_LEAD`);
- a user step is dated by the ACP `prompt_started` report of its Input;
- `timeline.py` sorts the root's steps by these clocks, so a step that started
  after the last prompt ended stands last. A child trajectory is sorted the
  same way and numbered from 1;
- when an Input has no `prompt_started` report, the user steps cannot be
  dated and the turn placement by identifier described below stands.

A step whose model call both `trace` and `network` hold takes its content from
the span. A model call only the wire holds takes its content from the wire
record; a tool call only ACP reported takes its title as tool name and its
`rawInput`, `rawOutput` or `content`.

Reply text of the root session that no model call carries is a step of its own
(`kind: acp_reply`), for example the ACP bridge's interruption notice.

The exported spans are read and assigned as follows:

- An inference span qualifies when `gen_ai.operation.name` marks an inference
  and `gen_ai.output.messages` holds an assistant message. The step takes its
  message, reasoning, tool calls, model name, token metrics and timestamp from
  that span. A span without an assistant message stays in
  `unassigned_agent_spans`: an aggregate usage span, or any call captured with
  content capture switched off.
- A tool result takes its content, status and clock from the tool span with the
  same `tool_call_id` as the model's call.
- Without any qualifying inference span the trajectory holds the user message
  only and reports `agent_otel_models_missing`.
- A span is exported when it ends, a run's own span last. An operation whose
  parent span never arrived reports `agent_otel_export_incomplete`: the export
  stopped before the run did, so later operations of that run, such as its
  final reply, may be absent from the trajectory.
- An exported span names no session and no Input. The Agent's ACP messages in
  `steps/NNNN/acp-events.jsonl` name the session that reported a tool call
  id. An inference takes the session of the
  tool calls it emitted, and an operation without one takes the only session
  known among the operations exported under the same parent span. The session
  and the folder of those messages place the step in its turn.
- The root execution owns a record that names a root session, or names none
  when no delegation was proposed. A delegation adapter may claim records for
  a child (see below).
- Reply text that exactly one model call carries gives that call the session
  that sent it. A model call only the wire holds runs in the execution that
  executed the tool calls it emitted, when they all ran in one.
- A record no rule assigns still becomes a step: it stands in the root
  trajectory with `extra.abb.owner: "unknown"` and an `unassigned_record`
  issue, and the document is `partial`. `unassigned_records` stays empty for
  this source; the `langgraph` source lists such records there instead.
- A record with neither session nor Input joins the turn only when the attempt
  has one Input and the unit declares `evaluation.single_input_model_scope =
  true`; the step then records `turn_evidence: isolated_single_input_case`.
  Otherwise it follows the turns instead of sitting inside one.

### OpenClaw child runs

The `openclaw` delegation adapter recognizes an accepted `sessions_spawn`
receipt and embeds a child trajectory. It attributes the child's operations in
one of two ways, both from recorded identifiers:

1. **Session.** An operation names the child session key of exactly one
   accepted receipt.
2. **Run structure**, for exports whose spans name no session
   (`diagnostics-otel` 2026.9.5), using span parent ids only:
   - every model call and tool execution is a child span of the
     `openclaw.run` it ran in;
   - a run is a child span of its `openclaw.harness.run`;
   - the harness span of a spawned run is a child span of the spawning run's
     harness span;
   - a nested run whose inference input carries the id of a tool call made in
     the spawning run continues that run's own conversation. OpenClaw starts
     such a run to tell the requester that its child finished. It is a
     further step of the spawning execution, not a child. OpenClaw replays
     history with tool call ids reduced to letters and digits, so ids are
     compared in that spelling, and only an unambiguous one counts. The rule
     applies only when every spawn of that run was `context: isolated`; a
     child that inherits the conversation would carry the same ids.

   When one run executed exactly one accepted spawn and exactly one other run
   is nested under its harness span, that nested run is the spawned child and its
   operations form the child trajectory. The delegation fact records
   `attribution: run_structure` and cites the child's run and harness spans.
   Any other count pairs nothing: the children keep their task step only, the
   operations stand in the root with `owner: "unknown"`, and the document reports
   `openclaw_child_run_ambiguous`. A child run that spawns again is resolved
   the same way, one level down.

Rule 2 was derived from recorded runs with one isolated spawn each, with and
without a completion notice; several spawns in one run, nested spawns and
inherited context are covered by synthetic tests only.

### Stored form

The converter builds and validates a complete document that embeds every record
it used. Before saving, `agentbench/trajectory/atif/slim.py` reduces it to the
stored form: the official ATIF fields unchanged and, under `extra.abb`, small
annotations plus pointers into the attempt directory, which keeps the complete
evidence.

A pointer is `{"file": "otel/spans.jsonl", "line": 19}`: the artifact path
relative to the attempt directory and a 1-based line, or `null` for a whole
JSON file. Every pointer must open an existing file and line, or the export
fails.

| Position | Stored under `extra.abb` | Not stored (read the attempt directory) |
| --- | --- | --- |
| Trajectory | `source`, `execution` (key and status), `provenance` (builder and Harbor versions), `issues`, `unassigned_records` (summary), `delegation_facts`, `version_missing_reason` | `raw_records`, `invocations`, `native_events`, `unassigned_agent_spans`, `auxiliary_artifacts` |
| Step | `evidence`, `input_id`, `kind`, `association`, `turn_evidence`, `result_source`, `execution_started_at`, `sources`, `owner` | `model_record`, `invocation`, `record_ids` |
| Tool call | `sources` (the records that hold its execution) | |
| Observation result | `evidence`, `execution_status`, `started_at`, `ended_at` | `tool_execution`, `record_ids` |
| Metrics | nothing | `recorded_usage` |
| Final metrics | `metrics_scope`, `unknown_model_usage` | |

The table mirrors the rule tables at the top of `slim.py`. Each `extra.abb` key
must have a rule there; a key without one fails the export, so storing new
data is a deliberate change to that file. Record conservation and ownership are
validated on the complete document before it is reduced.

Known gaps of the automatic document:

- With `langgraph`, user and `invocation_result` steps have no timestamp, and
  neither does a callback step without one linked Agent-exported span. The
  per-Input OTel files that used to supply those clocks are no longer written.
- With `acp_otel`, an ACP Agent that exports no OTel still reports
  `agent_otel_models_missing`; its steps then come from the wire and ACP alone.
  Several OpenClaw children spawned by one run cannot be told apart: their
  operations stand in the root with `owner: "unknown"`.
- A step marked `owner: "unknown"` may belong to a child. A reader of the root
  trajectory must not take it for an action of the root Agent.
- `NETWORK_LEAD` is one constant. The recorded leads ranged from 43 to 800 ms,
  so a step only the wire holds can stand slightly before or after a step
  dated by another clock.
- Two model calls with the same text and no tool call pair in recorded order.
  Reply text that two model calls carry is merged into the earlier one and
  gives neither a session.
- OpenClaw's last export batch was lost in one recorded run when the Agent
  process group was killed after the default 3 s `cleanup_timeout`; the unit
  now sets 10 s. A lost batch removes the root run's final reply and its run
  spans, leaving run-structure attribution nothing to follow;
  `agent_otel_export_incomplete` reports it.
- With a completion notice, the last model step of the turn is OpenClaw's
  `NO_REPLY` to that notice, after the step that answered the user.
- ABB ends an Input at the ACP prompt response. After `sessions_yield`,
  OpenClaw's requester answers in a later run (about 12 s later in one
  recorded run) that is not sent over ACP; ABB has stopped the Agent by then,
  so neither the delivered result nor the trajectory holds that answer.
- Host redaction replaces `childSessionKey` in a recorded receipt, so the
  session rule cannot use it; the run ID survives.

The official [Harbor Trajectory model at the pinned commit](https://github.com/harbor-framework/harbor/blob/ec6aeab7fe0eb51df52b4e72c524daf5ea9cc5f4/src/harbor/models/trajectories/trajectory.py)
provides schema validation and embedded child trajectories. The converter uses
its actual `Agent`, `Step`, `ToolCall`, `ObservationResult`, and
`SubagentTrajectoryRef` models. There is no replacement public trajectory schema.

| File | Responsibility |
| --- | --- |
| `agentbench/trajectory/atif/contracts.py` | Internal evidence, execution identity, delegation proposals, issues, and export result dataclasses. |
| `reader.py` | Guarded source reads, three ABB layouts, Inputs, ACP events, session binding, and auxiliary OTel/runtime evidence. |
| `sources/__init__.py`, `sources/base.py` | Step-source factory, contract, and the record builders for exported spans. |
| `sources/langgraph.py` | Callback step records: exact model/framework merging, interrupted streams, chain records. |
| `sources/acp_otel.py` | Exported-span step records for ACP Agents and session inheritance. |
| `sources/merge.py` | Wire model calls and ACP tool reports as records; pairing with the exported records; `sources` and clocks. |
| `timeline.py` | Root steps of a merged source in clock order: user steps at `prompt_started`, unclaimed ACP reply text. |
| `adapters/base.py`, `adapters/__init__.py` | Delegation protocol and explicitly selected Strategy registry. |
| `adapters/deepagents.py` | Tool-to-named-agent graph boundaries using parent spans, actual entry metadata, and delegation arguments. |
| `adapters/opencode.py` | Structured task/session metadata; optional explicit native turn/provider-response identity. Missing internals remain a reported gap. |
| `hierarchy.py` | One ancestry/ownership resolver, scope checks, nearest confirmed child, cycle/conflict rejection, and scoped existing tool association. |
| `assembler.py` | Official ATIF steps, observations, nested children, exact runtime result placement, full input context, and unknown records. |
| `provenance.py` | Historical source digests, frozen target revision, unavailable provenance, converter source digests, and installed Harbor commit verification. |
| `validation.py` | Official validation, record conservation, reference integrity, ownership agreement, and raw evidence inventory. |
| `export.py` | Offline pipeline, source immutability checks, UTF-8, atomic final publication, and failure reports. |
| `slim.py` | Stored form: one rule table per position, evidence pointers, and pointer checks. |
| `agentbench/observe/tool_links.py` | Adds optional `scope_keys`; callers omitting it retain the original behavior. |
| `agentbench/experiments/atif/__main__.py` | Thin explicit `export`, `run`, and `verify` command dispatch. |
| `runner.py` | Existing ABB runtime/adapter orchestration, configured workspace, read-only native configuration overrides, and controlled cancellation. |
| `acceptance.py` | Rebuild comparison, source-content checks, actual file outcomes, and configured acceptance conditions. |
| `tests/atif_fixtures.py`, `tests/test_atif_*.py` | Synthetic edge cases and the historical two-child acceptance case. |
| `tests/test_emitted_tool_links.py` | Default-scope regression and unknown-candidate preservation. |

## Identity and evidence rules

One saved run/attempt produces a root trajectory. A confirmed child execution
has its own stable identifier, independent step numbering, and a parent reference
on the delegation observation. IDs include recorded run/attempt scope, invocation,
source and native execution identity. Recorded native IDs, Agent IDs, invocation
IDs, and exported trajectory IDs are separate fields. Source filenames qualify
framework spans; display names and export time never generate identity.

The Deep Agents adapter recognizes recorded contracts, not mini-opencode's name,
UUID values, or test labels. Middleware spans remain ancestry, not new Agents.
Disconnected/cyclic ancestry and conflicting boundaries never fall back to root
ownership. Unknown tool executions remain candidates during scoped matching,
preventing a falsely unique tool association.

The trace inventory links compatible network and framework spans and retains
transport retries. Starting with builder version 4, ATIF assembly uses the
native evidence before that join. An interceptor request or response cannot
supply an ATIF step, system prompt, tool call or usage. The portable bundle
keeps the transport evidence under `runs/`. A recorded outward reply can
supply an agent step independently of model ownership.

User inputs and observed initial system messages become steps. Full model
messages/tools/parameters remain in `Step.extra.abb.model_record`. Repeated model
history is not emitted again as new conversation. Child input is the actual entry
input when observed, separately from the parent's delegation description.

Incomplete arguments retain their original fragments. Missing results, tool
errors, interrupted models, and cancelled runs retain distinct statuses. Unknown
model call counts are not set to zero. Only recorded usage/cost is exported;
incomplete totals are not presented as full totals.

Normalized operations with unknown execution ownership are retained in root
`extra.abb.unassigned_records`. Native JSONL records, including malformed final
lines, chain events, and OTel envelopes, are preserved in `extra.abb.raw_records`.
Auxiliary OTel payloads/runtime/configuration facts are retained separately.
The association report accounts for every raw source position as assigned or
unknown; auxiliary records are not promoted into additional model/tool steps.
Generic ATIF viewers may not display these ABB extension fields.

Agent revision comes only from the run's frozen target. Missing historical
version is `unknown`, with a reported reason. Missing collector/image identity
remains unavailable. The current registry is never used to relabel history.
Converter code digests and the Harbor commit identify the derivation separately.

## Acceptance performed on 2026-11-15

Host: macOS arm64, Python 3.14.6. Agent runtimes: Docker Linux containers.
Model for the live runs: OpenRouter `openai/gpt-5.5`. Actual invocation counts
are outcomes of those executions, not generic acceptance thresholds.

| Evidence | Models | Tools | Embedded children | Outcome |
| --- | ---: | ---: | ---: | --- |
| Historical two-child run | 11 | 12 | 2 | Parent 3, children 4 each; 59 source-content checks pass. |
| Standalone mini-opencode | 11 | 13 | 2 | Parent 3, children 4 each; both final files and absent drafts verified on the host. |
| Standalone OpenCode ACP | 10 | 5 | 0 | Two recorded task/session delegations and actual file outcomes pass; all 10 network models remain explicitly unassigned. Valid partial ATIF. |
| mini-opencode cancellation | 1 | 0 | 0 | Cancellation after saved stream deltas; 167 characters of partial model output retained; no fabricated final success. |

Final artifacts are under ignored `cache/atif/final-v3/`:

```text
final-v3/
  acceptance-report.json
  history/    # ATIF, source manifest, association, validation, verification
  langgraph/
  acp/
  cancel/
```

Each verification report compares raw model requests/responses and tool
arguments/results with their exported evidence, as well as counts and ownership.
The historical fixture retains original IDs/structure. Its worker JSONL is native
ABB evidence; interceptor payloads were extracted from the existing App event
journal into ABB transport envelopes. This transport conversion is disclosed in
the fixture manifest; the old App trajectory was not used as ground truth.

Original live run directories, including unsuccessful trials, remain preserved:

| Directory / run | Result |
| --- | --- |
| `cache/atif/live-01/de30f01161ba49baaed40fd56fdecfd6` | Accepted LangGraph file run. |
| `cache/atif/live-01/229038491f004298805206e8b7e5ceee` | Initial harness sent an object to an ACP text input; failed before model calls. Runner now derives input shape from the manifest. |
| `cache/atif/live-01/83611da90e00468c970427bc7915444d` | Initial cancellation probe used native non-streaming configuration; interrupted through experiment cleanup. |
| `cache/atif/live-02/307fa907fc3e4e33b67d0388f8c2467c` | OpenCode children reported that the restricted task root did not exist. Runner now prepares that isolated directory. |
| `cache/atif/live-02/95770c287b76420ca83a95c4dfa78b98` | Accepted native-streaming cancellation run. |
| `cache/atif/live-03/827d2a26eae944278dbe87dd5cefa416` | Accepted ACP file outcomes with declared telemetry gaps. |

These were explicit corrections and selective reruns, not hidden automatic model
retries. Source evidence and earlier exports were not overwritten. Only experiment
resources were cleaned up; both containers present before the experiment remained
running afterward.

## ACP coverage and deferred work

The fixed OpenCode version records task metadata with parent and child session
IDs in ACP `rawOutput.metadata`. Two distinct child sessions were observed, and
their returned results and independently inspected files establish task outcomes.
ABB's ACP trace includes main-session tool notifications, but no child-internal
framework spans or explicit network-call-to-child mapping for this run. The
converter therefore emits no empty/fabricated child trajectory. The 10 network
calls remain complete recorded evidence with unknown execution ownership.

The optional native association branch is covered by synthetic contract tests,
not by this OpenCode execution. It requires structured native session/turn and
unique provider response identities; repeated-session ambiguity is rejected.

Network model truncation and further network/subagent correlation work are
deferred as requested. Candidate future collection work would need to preserve
child turn/delegation identity, child internal model/tool events, and an explicit
wire-to-native-call identity. No new collector fields or Agent-specific matching
heuristics were introduced in this experiment.

## Regression and platform limits

97 relevant tests passed in the isolated environment, covering layouts, nested
children, name/ID reuse, unknown candidates, broken/cyclic/conflicting ancestry,
stream cancellation, partial arguments, source changes, UTF-8, historical
versions, schema/references, and existing trajectory/serialization/identity rules.
The original ABB environment also passed all 63 selected existing regression
tests. It still imports its trajectory module and exposes its
unchanged CLI without Harbor installed. Native Windows/Linux execution has not
been tested. The successful Linux Agent containers on macOS do not establish
native Linux or Windows host compatibility.

The full implementation patch and file inventory are generated under
`cache/atif/final-v3/implementation.patch` and `file-inventory.json`. No commit or
push was performed. App integration, live UI, default exports, and Judge input
changes remain outside this experiment.


## Portable trace bundle mode

The opt-in `--bundle` mode retains official ATIF content and externalizes diagnostic
copies into portable, losslessly verifiable trace references. See [the bundle
contract and commands](Portable-Trace-Bundles.md). Legacy exports remain available.

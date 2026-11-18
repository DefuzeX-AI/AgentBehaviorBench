# ABB ATIF and subagent association experiment

## Scope and implementation

This is an explicit host-side experiment. It leaves `trajectory/builder.py`,
`trajectory/schema.py`, default run export hooks, Judge/GT contracts, collectors,
Agent definitions, and the desktop application unchanged. Harbor is installed only
in `cache/atif/venv`, not ABB's default environment or any Agent image.

The official [Harbor Trajectory model at the pinned commit](https://github.com/harbor-framework/harbor/blob/ec6aeab7fe0eb51df52b4e72c524daf5ea9cc5f4/src/harbor/models/trajectories/trajectory.py)
provides schema validation and embedded child trajectories. The converter uses
its actual `Agent`, `Step`, `ToolCall`, `ObservationResult`, and
`SubagentTrajectoryRef` models. There is no replacement public trajectory schema.

| File | Responsibility |
| --- | --- |
| `agentbench/trajectory/atif/contracts.py` | Internal evidence, execution identity, delegation proposals, issues, and export result dataclasses. |
| `reader.py` | Guarded source reads, three ABB layouts, exact model/framework merging, interrupted streams, chain records, ACP events, and auxiliary OTel/runtime evidence. |
| `adapters/base.py`, `adapters/__init__.py` | Delegation protocol and explicitly selected Strategy registry. |
| `adapters/deepagents.py` | Tool-to-named-agent graph boundaries using parent spans, actual entry metadata, and delegation arguments. |
| `adapters/opencode.py` | Structured task/session metadata; optional explicit native turn/provider-response identity. Missing internals remain a reported gap. |
| `hierarchy.py` | One ancestry/ownership resolver, scope checks, nearest confirmed child, cycle/conflict rejection, and scoped existing tool association. |
| `assembler.py` | Official ATIF steps, observations, nested children, exact runtime result placement, full input context, and unknown records. |
| `provenance.py` | Historical source digests, frozen target revision, unavailable provenance, converter source digests, and installed Harbor commit verification. |
| `validation.py` | Official validation, record conservation, reference integrity, ownership agreement, and raw evidence inventory. |
| `export.py` | Offline pipeline, source immutability checks, UTF-8, atomic final publication, and failure reports. |
| `agentbench/observe/tool_links.py` | Adds optional `scope_keys`; callers omitting it retain the original behavior. |
| `agentbench/experiments/atif/__main__.py` | Thin explicit `export`, `run`, and `verify` command dispatch. |
| `runner.py` | Existing ABB runtime/adapter orchestration, configured workspace, read-only native configuration overrides, and controlled cancellation. |
| `acceptance.py` | Rebuild comparison, source-content checks, actual file outcomes, and configured acceptance conditions. |
| `experiments/atif/` | Pinned dependency input/lock, declarative Agent/model references, prompts, and reproducible instructions. |
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
